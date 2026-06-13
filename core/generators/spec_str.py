"""구조 스펙 기반 문자열 해시 생성기.

기본 목표: 구조 정보만으로 '완전 해시(충돌 0)'를 만든다.
구조만으로 만드는 완전 해시 = 혼합 진법 패킹(각 세그먼트를 진법 값으로 환산해
자리값으로 결합 → 키공간 [0, domain) 으로의 전단사). 비둘기집 원리상 domain보다
작은 테이블에 충돌 없이 담는 것은 불가능하므로, 완전 해시의 테이블 크기 = domain.

전략 선택:
  (A) packed-dense  : domain ≤ pack_max(그리고 ≤ 2^32). 최소 완전 해시, uint32,
                      반환값이 곧 0..domain-1 의 밀집 인덱스.
  (B) packed-wide   : pack_max < domain < 2^64. 완전 해시(충돌 0)이지만 밀집은
                      아님. uint64 고유 인덱스 반환(희소 테이블/64비트 키로 사용).
  (C) byte-hash     : domain ≥ 2^64 또는 가변 길이. 구조만으로는 완전 해시 불가 →
                      일반(균일) 해시로 폴백. 충돌이 있을 수 있음(경고). 실제 키
                      목록이 있으면 Perfect 모드 사용 권장.
"""
from __future__ import annotations

from ..keysim import SimResult, group_ranges, simulate
from ..keyspec import KeySpec, parse_keyspec
from .base import CodeBundle, Generator

_INIT = {"fnv1a": "2166136261u", "djb2": "5381u"}
_U32 = 1 << 32
_U64 = 1 << 64


def _step(algo: str, byte_expr: str, indent: str) -> str:
    if algo == "fnv1a":
        return f"{indent}h ^= {byte_expr};  h *= 16777619u;\n"
    return f"{indent}h = ((h << 5) + h) + {byte_expr};  /* h*33 + b */\n"


class SpecStringGenerator(Generator):
    def generate(self) -> CodeBundle:
        cfg = self.cfg
        spec = parse_keyspec(cfg.key_spec)
        pack_max = cfg.pack_max_domain or (1 << 22)
        domain = spec.packing_domain()

        if domain is not None and domain > 1:
            if domain <= min(pack_max, _U32):
                return self._generate_packed(spec, domain, wide=False)
            if domain < _U64:
                return self._generate_packed(spec, domain, wide=True)
        return self._generate_bytehash(spec, domain)

    # ===================== (A,B) packed-index (완전 해시) =====================
    def _generate_packed(self, spec: KeySpec, domain: int, wide: bool) -> CodeBundle:
        cfg = self.cfg
        fn = cfg.func_name
        prefix = cfg.macro_prefix
        segs = spec.packable_segments()
        ret_type = "uint64_t" if wide else "uint32_t"
        suffix = "ull" if wide else "u"
        mul_suffix = "ull" if wide else "u"

        # 동일 charset 은 rank 테이블 공유
        tables, order = {}, []
        for s in segs:
            if s.charset not in tables:
                tables[s.charset] = (f"{fn}_r{len(order)}", sorted(s.charset))
                order.append(s.charset)
        table_c = "".join(
            self._rank_table_c(tables[cs][0], tables[cs][1]) + "\n" for cs in order)

        body = ["    const unsigned char *p = (const unsigned char *)s;\n",
                f"    {ret_type} idx = 0;\n"]
        for s in segs:
            name = tables[s.charset][0]
            body.append(
                f"    /* off {s.start}..{s.start + s.min_len - 1}, base {s.cardinality} */\n")
            for off in range(s.start, s.start + s.min_len):
                body.append(f"    idx = idx * {s.cardinality}{mul_suffix} + {name}[p[{off}]];\n")

        kind = "minimal" if not wide else "perfect(64-bit, sparse)"
        banner = self._packed_comment(spec, segs, domain, wide)
        defines = (
            f"#define {prefix}_TABLE_SIZE {domain}{suffix}  "
            f"/* mixed-radix domain ({kind}) */\n")
        signature = f"{ret_type} {fn}(const char *s)"

        src = (
            f"{self._file_banner()}"
            f"{banner}"
            f'#include "{fn}.h"\n\n'
            f"{table_c}"
            f"{signature} {{\n"
            f"{''.join(body)}"
            f"    return idx;\n"
            f"}}\n"
        )
        header = self._wrap_header(f"{defines}\n{signature};\n")

        warnings = [
            "packed-index: 키가 스펙을 정확히 따른다고 가정합니다(범위 밖 문자는 rank 0)."
        ]
        if wide:
            warnings.append(
                f"도메인({domain})이 pack_max를 초과 → 밀집 테이블 불가. 충돌 0의 64비트 "
                "고유 인덱스를 반환합니다(희소 테이블/키로 사용). 밀집 인덱스가 필요하면 "
                "pack_max를 키우거나 스펙을 줄이세요.")
        return CodeBundle(
            header=header, source=src,
            stats={
                "strategy": "packed-dense" if not wide else "packed-wide",
                "perfect": True,
                "collisions": 0,
                "table_size": domain,
                "return_type": ret_type,
                "bytes_per_key": sum(s.min_len for s in segs),
                "segments_packed": len(segs),
            },
            warnings=warnings,
        )

    def _rank_table_c(self, name: str, chars) -> str:
        rank = [0] * 256
        for i, ch in enumerate(chars):
            rank[ord(ch) & 0xFF] = i
        nums = ", ".join(str(v) for v in rank)
        return (
            f"/* rank table for charset of size {len(chars)} "
            f"({''.join(chars[:8])}{'...' if len(chars) > 8 else ''}) */\n"
            f"static const uint8_t {name}[256] = {{ {nums} }};\n")

    def _packed_comment(self, spec, segs, domain, wide) -> str:
        seg_lines = []
        for i, s in enumerate(spec.segments):
            tag = "packed" if s in segs else "skipped(const)"
            seg_lines.append(
                f" *   [{i}] off={s.start} len={s.length_label()} "
                f"card={s.cardinality} -> {tag}\n")
        kind = ("minimal perfect (dense, returns table index)" if not wide
                else "perfect, collision-free 64-bit index (sparse)")
        return (
            "/*\n"
            " * Structure-driven hash: PACKED-INDEX (mixed-radix) -- PERFECT (zero collisions).\n"
            f" * Type: {kind}\n"
            " * Each segment -> base-N value, combined positionally => bijection onto [0,domain).\n"
            " * Segments:\n"
            f"{''.join(seg_lines)}"
            f" * domain = {domain}, bytes/key = {sum(s.min_len for s in segs)}\n"
            " */\n"
        )

    # ===================== (C) byte-hash (완전 해시 아님) =====================
    def _generate_bytehash(self, spec: KeySpec, domain) -> CodeBundle:
        cfg = self.cfg
        sim = simulate(spec, max(2, cfg.expected_keys or 1000), seed=cfg.seed or 1)
        fn = cfg.func_name
        prefix = cfg.macro_prefix

        banner = self._bytehash_comment(spec, sim, domain)
        defines = f"#define {prefix}_TABLE_SIZE {sim.table_size}u  /* power of two */\n"
        signature = f"uint32_t {fn}(const char *s)"

        if sim.variable:
            body, extra_inc = self._emit_variable(sim, prefix)
        else:
            body, extra_inc = self._emit_fixed(sim, prefix)

        src = (
            f"{self._file_banner()}"
            f"{banner}"
            f'#include "{fn}.h"\n'
            f"{extra_inc}\n"
            f"{signature} {{\n"
            f"{body}"
            f"    return h & ({prefix}_TABLE_SIZE - 1u);\n"
            f"}}\n"
        )
        header = self._wrap_header(f"{defines}\n{signature};\n")

        warnings = list(sim.notes)
        reason = "가변 길이(키공간 무한)" if spec.has_variable else f"도메인({domain})이 2^64 이상"
        warnings.insert(0, (
            f"완전 해시가 아닙니다: {reason}이라 구조만으로 충돌 0을 보장할 수 없어 "
            "일반(균일) 해시로 생성했습니다. 충돌 0이 필요하면 실제 키 목록으로 "
            "Perfect 모드를 쓰거나, 고정 길이/작은 스펙으로 줄이세요."))

        return CodeBundle(
            header=header, source=src,
            stats={
                "strategy": "byte-hash",
                "perfect": False,
                "algorithm": sim.algorithm,
                "variable": sim.variable,
                "bytes_per_key": f"{sim.bytes_per_key:.1f}/{sim.full_bytes}",
                "speedup": f"{sim.speedup:.2f}x",
                "table_size": sim.table_size,
                "prehash_collisions": sim.prehash_collisions,
                "chi/dof": f"{sim.chi_norm:.3f}",
                "samples": sim.sample_size,
            },
            warnings=warnings,
        )

    def _emit_fixed(self, sim: SimResult, prefix: str):
        lines = [
            "    const unsigned char *p = (const unsigned char *)s;\n",
            f"    uint32_t h = {_INIT[sim.algorithm]};\n",
            f"    /* selected offsets: {', '.join(map(str, sim.offsets))} */\n",
        ]
        for start, length in group_ranges(sim.offsets):
            if length <= 3:
                for off in range(start, start + length):
                    lines.append(_step(sim.algorithm, f"p[{off}]", "    "))
            else:
                lines.append(f"    for (int i = {start}; i < {start + length}; i++) {{\n")
                lines.append(_step(sim.algorithm, "p[i]", "        "))
                lines.append("    }\n")
        return "".join(lines), ""

    def _emit_variable(self, sim: SimResult, prefix: str):
        lines = [
            "    const unsigned char *p = (const unsigned char *)s;\n",
            "    size_t n = strlen(s);\n",
            f"    uint32_t h = {_INIT[sim.algorithm]};\n",
        ]
        if sim.offsets:
            lines.append(
                f"    /* fixed offsets (bounds-checked): "
                f"{', '.join(map(str, sim.offsets))} */\n")
            for start, length in group_ranges(sim.offsets):
                end = start + length
                lines.append(f"    for (size_t i = {start}; i < {end} && i < n; i++) {{\n")
                lines.append(_step(sim.algorithm, "p[i]", "        "))
                lines.append("    }\n")
        if sim.tail_start is not None:
            lines.append(f"    /* variable tail: offset {sim.tail_start}..end */\n")
            lines.append(f"    for (size_t i = {sim.tail_start}; i < n; i++) {{\n")
            lines.append(_step(sim.algorithm, "p[i]", "        "))
            lines.append("    }\n")
        return "".join(lines), "#include <string.h>\n"

    def _bytehash_comment(self, spec, sim: SimResult, domain) -> str:
        seg_lines = []
        for i, s in enumerate(spec.segments):
            seg_lines.append(
                f" *   [{i}] off={s.start} len={s.length_label()} card={s.cardinality} "
                f"entropy={s.entropy_bits:.1f}b ({s.label})\n")
        tail_txt = f" tail_from={sim.tail_start}" if sim.tail_start is not None else ""
        reason = "variable length (infinite keyspace)" if spec.has_variable \
            else f"domain {domain} >= 2^64"
        return (
            "/*\n"
            " * Structure-driven hash: BYTE-HASH (general, NOT collision-free).\n"
            f" * Reason for fallback: {reason}.\n"
            f" * Mode: {'variable-length (bounds-checked)' if sim.variable else 'fixed-length'}\n"
            " * Segments:\n"
            f"{''.join(seg_lines)}"
            f" * selected = {sim.bytes_per_key:.1f}/{sim.full_bytes} bytes avg, "
            f"{sim.selected_entropy:.1f} bits{tail_txt}  (speedup {sim.speedup:.2f}x)\n"
            f" * table M = {sim.table_size} (pow2), algo = {sim.algorithm}\n"
            f" * simulation (N={sim.sample_size}): prehash_collisions="
            f"{sim.prehash_collisions}, chi2/dof={sim.chi_norm:.3f} (1.0=uniform)\n"
            " */\n"
        )
