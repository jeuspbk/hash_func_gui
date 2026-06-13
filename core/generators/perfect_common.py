"""Perfect Hash 공통 로직 (CHD-lite: hash-and-displace + rank 압축).

알고리즘
--------
1차: bucket = base_hash(key, SEED0) % R          (키를 버킷에 분배)
2차: 버킷을 크기 내림차순으로, 각 버킷마다 변위 시드 d 를 0,1,2…로 증가시키며
     base_hash(key, d) % M_RAW 가 (버킷 내부 유일 + 미점유) 슬롯이 되도록 배치.

핵심: 탐색은 **여유 있는 슬롯**(부하율 ~0.5, M_RAW ≈ 2n)에서 수행해 안정적으로
수렴시킨다. 부하율 1.0(M=n)은 greedy 가 자주 실패하는 어려운 영역이라 피한다.

minimal 요청 시: 점유 슬롯들의 등장 순서를 매긴 rank[] 테이블로 0..n-1 로 압축한다.
  final_index(key) = rank[ base_hash(key, disp[bucket]) % M_RAW ]

파이썬에서 탐색/검증을 끝내고 테이블만 C로 방출하므로, C의 base hash는
hashers.base_hash 와 비트 단위로 동일해야 한다.
"""
from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from typing import List, Optional

from ..config import HashConfig
from ..hashers import base_hash
from .base import CodeBundle, Generator

_DISPLACEMENT_CAP = 1 << 20  # 버킷당 변위 시드 탐색 상한 (저부하라 거의 안 닿음)
_SEED0_ATTEMPTS = 64  # 1차 시드 재시도 횟수
_LOAD = 0.5  # 탐색 시 목표 부하율 (M_RAW ≈ n / _LOAD)
_AVG_BUCKET = 4  # 1차 버킷 평균 크기 (저부하라 4 정도도 쉽게 수렴, 테이블도 작음)


class PerfectHashError(Exception):
    """주어진 파라미터로 완전 해시를 찾지 못함."""


@dataclass
class PerfectTable:
    seed0: int
    buckets: int  # R
    m_raw: int  # 탐색용 슬롯 수
    final_size: int  # 최종 해시값 범위 (minimal이면 n)
    displacement: List[int]  # 길이 R
    rank: Optional[List[int]]  # 길이 m_raw, slot→최종 인덱스 (minimal일 때만)
    raw_slots: List[Optional[int]]  # 길이 m_raw, 각 슬롯의 원본 키 인덱스
    max_displacement: int
    attempts: int
    minimal: bool


def build_perfect(cfg: HashConfig) -> PerfectTable:
    keys = cfg.keys
    n = len(keys)
    m_raw = max(1, max(n, int(n / _LOAD) + 1))
    r = max(1, n // _AVG_BUCKET + 1)
    ci = cfg.key_type == "string" and cfg.case_insensitive

    def bh(key, seed):
        return base_hash(key, seed, key_type=cfg.key_type, case_insensitive=ci)

    for attempt in range(_SEED0_ATTEMPTS):
        seed0 = attempt  # 결정적: 0,1,2,...
        result = _try_build(keys, m_raw, r, seed0, bh)
        if result is None:
            continue
        displacement, raw_slots, max_d = result

        if cfg.minimal:
            rank = [0] * m_raw
            c = 0
            for s in range(m_raw):
                rank[s] = c  # 점유 슬롯 s의 최종 인덱스 = 그 앞의 점유 슬롯 수
                if raw_slots[s] is not None:
                    c += 1
            final_size = n
        else:
            rank = None
            final_size = m_raw

        return PerfectTable(
            seed0=seed0, buckets=r, m_raw=m_raw, final_size=final_size,
            displacement=displacement, rank=rank, raw_slots=raw_slots,
            max_displacement=max_d, attempts=attempt + 1, minimal=cfg.minimal,
        )

    raise PerfectHashError(
        f"{_SEED0_ATTEMPTS}회 시도 후에도 완전 해시를 찾지 못했습니다 (키 {n}개). "
        f"키 목록에 중복/유사 키가 많은지 확인하세요."
    )


def _try_build(keys, m_raw, r, seed0, bh):
    buckets: List[List[int]] = [[] for _ in range(r)]
    for idx, key in enumerate(keys):
        buckets[bh(key, seed0) % r].append(idx)

    order = sorted(range(r), key=lambda b: len(buckets[b]), reverse=True)

    raw_slots: List[Optional[int]] = [None] * m_raw
    displacement = [0] * r
    max_d = 0

    for b in order:
        members = buckets[b]
        if not members:
            continue
        d = 0
        while d < _DISPLACEMENT_CAP:
            chosen = []
            local = set()
            ok = True
            for idx in members:
                slot = bh(keys[idx], d) % m_raw
                if slot in local or raw_slots[slot] is not None:
                    ok = False
                    break
                local.add(slot)
                chosen.append((slot, idx))
            if ok:
                for slot, idx in chosen:
                    raw_slots[slot] = idx
                displacement[b] = d
                max_d = max(max_d, d)
                break
            d += 1
        else:
            return None  # 이 seed0 로는 실패 → 다음 seed0

    return displacement, raw_slots, max_d


# --- C 코드 조각 ---

def emit_base_hash_c(fn: str, key_type: str, case_insensitive: bool) -> str:
    if key_type == "string":
        tolower = ""
        if case_insensitive:
            tolower = "        if (c >= 'A' && c <= 'Z') c += 32;  /* ASCII tolower */\n"
        return (
            f"static uint64_t {fn}_bh(const char *s, uint64_t seed) {{\n"
            f"    uint64_t h = 1469598103934665603ULL ^ seed;\n"
            f"    while (*s) {{\n"
            f"        uint64_t c = (unsigned char)*s++;\n"
            f"{tolower}"
            f"        h ^= c;\n"
            f"        h *= 1099511628211ULL;\n"
            f"    }}\n"
            f"    return h;\n"
            f"}}\n"
        )
    return (
        f"static uint64_t {fn}_bh(uint64_t x, uint64_t seed) {{\n"
        f"    x += seed;\n"
        f"    x ^= x >> 33;  x *= 0xff51afd7ed558ccdULL;\n"
        f"    x ^= x >> 33;  x *= 0xc4ceb9fe1a85ec53ULL;\n"
        f"    x ^= x >> 33;\n"
        f"    return x;\n"
        f"}}\n"
    )


def format_array(name: str, ctype: str, values: List[int]) -> str:
    items = ", ".join(str(v) for v in values)
    return f"static const {ctype} {name}[{len(values)}] = {{ {items} }};\n"


class PerfectGeneratorBase(Generator):
    """int/str 공통 Perfect Hash 생성. 키타입별 차이는 추상 메서드로 분리."""

    @abstractmethod
    def _arg_signature(self) -> str:
        """함수 인자 선언 (변수명은 반드시 `key`). 예: 'const char *key'."""

    @abstractmethod
    def _verify_ctype(self) -> str:
        """검증 테이블 원소 타입. 예: 'const char *' 또는 'uint64_t'."""

    @abstractmethod
    def _key_literal(self, key) -> str:
        """C 리터럴로 변환."""

    @abstractmethod
    def _compare_expr(self, arr_elem: str) -> str:
        """검증 비교식."""

    @abstractmethod
    def _empty_literal(self) -> str:
        """검증 테이블 빈 슬롯 표시값 (string: NULL, int: sentinel)."""

    @abstractmethod
    def _is_empty_expr(self, arr_elem: str) -> str:
        """빈 슬롯 판정식."""

    def _verify_extra_includes(self) -> str:
        return ""

    # --- 공통 생성 ---
    def generate(self) -> CodeBundle:
        cfg = self.cfg
        table = build_perfect(cfg)

        placed = [s for s in table.raw_slots if s is not None]
        collisions = len(placed) - len(set(placed))  # 정상이면 0

        fn = cfg.func_name
        prefix = cfg.macro_prefix
        ret_type = self._uint_type()
        ret_cast = "(uint32_t)" if cfg.output_bits == 32 else ""
        ci = cfg.key_type == "string" and cfg.case_insensitive

        signature = f"{ret_type} {fn}({self._arg_signature()})"

        defines = (
            f"#define {prefix}_SIZE {table.final_size}u\n"
            f"#define {prefix}_RAW {table.m_raw}u\n"
            f"#define {prefix}_SEED0 {table.seed0}ULL\n"
            f"#define {prefix}_BUCKETS {table.buckets}u\n"
        )

        bh_c = emit_base_hash_c(fn, cfg.key_type, ci)
        disp_c = format_array(f"{fn}_disp", "uint32_t", table.displacement)
        rank_c = ""
        if table.minimal:
            rank_c = format_array(f"{fn}_rank", "uint32_t", table.rank) + "\n"

        # 최종 반환식
        if table.minimal:
            ret_inner = f"{fn}_rank[slot]"
        else:
            ret_inner = "slot"
        lookup_body = (
            f"{signature} {{\n"
            f"    uint64_t b = {fn}_bh(key, {prefix}_SEED0) % {prefix}_BUCKETS;\n"
            f"    uint64_t slot = {fn}_bh(key, {fn}_disp[b]) % {prefix}_RAW;\n"
            f"    return {ret_cast}{ret_inner};\n"
            f"}}\n"
        )

        # 선택: 미지 키 구분용 검증 테이블 + lookup (최종 인덱스로 정렬, 크기 = SIZE)
        verify_c = ""
        verify_proto = ""
        verify_includes = ""
        if cfg.emit_verify_table:
            ctype = self._verify_ctype()
            elems = [self._empty_literal()] * table.final_size
            for slot, idx in enumerate(table.raw_slots):
                if idx is None:
                    continue
                final_idx = table.rank[slot] if table.minimal else slot
                elems[final_idx] = self._key_literal(cfg.keys[idx])
            arr = ", ".join(elems)
            verify_c = (
                f"static const {ctype} {fn}_keys[{prefix}_SIZE] = {{ {arr} }};\n\n"
                f"int {fn}_lookup({self._arg_signature()}) {{\n"
                f"    uint32_t i = (uint32_t){fn}(key);\n"
                f"    if (i >= {prefix}_SIZE || {self._is_empty_expr(f'{fn}_keys[i]')}) "
                f"return -1;\n"
                f"    return {self._compare_expr(f'{fn}_keys[i]')} ? (int)i : -1;\n"
                f"}}\n"
            )
            verify_proto = f"int {fn}_lookup({self._arg_signature()});\n"
            verify_includes = self._verify_extra_includes()

        src = (
            f"{self._file_banner()}"
            f'#include "{fn}.h"\n'
            f"{verify_includes}\n"
            f"{bh_c}\n"
            f"{disp_c}\n"
            f"{rank_c}"
            f"{verify_c}\n"
            f"{lookup_body}"
        )

        header = self._wrap_header(f"{defines}\n{signature};\n{verify_proto}")

        warnings = []
        if collisions:
            warnings.append(f"내부 오류: 충돌 {collisions}건 (버그 가능성).")
        if ci and any(ord(ch) > 127 for k in cfg.keys for ch in str(k)):
            warnings.append(
                "대소문자 무시 + 비ASCII 키: 파이썬 lower와 C ASCII tolower 동작이 "
                "다를 수 있습니다."
            )

        return CodeBundle(
            header=header,
            source=src,
            stats={
                "collisions": collisions,
                "size": table.final_size,
                "raw_slots": table.m_raw,
                "buckets": table.buckets,
                "seed0": table.seed0,
                "max_disp": table.max_displacement,
                "minimal": cfg.minimal,
                "keys": len(cfg.keys),
            },
            warnings=warnings,
        )
