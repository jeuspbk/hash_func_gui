"""구조분석(spec) 모드 검증: 고정/가변 길이 스펙으로 생성한 C 코드를 컴파일/실행.

생성된 C 해시가 스펙 샘플 키(가변 길이 포함)에 대해 파이썬 시뮬레이션과
동일한 테이블 인덱스를 내는지(= C/파이썬 비트 일치) 확인한다.
"""
from __future__ import annotations

import os
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
BUILD = os.path.join(ROOT, "build")

from core.config import HashConfig  # noqa: E402
from core.generators import generate  # noqa: E402
from core.keysim import _ALGOS, _processed_bytes, _sample_keys, simulate  # noqa: E402
from core.keyspec import parse_keyspec  # noqa: E402


def _c_lit(s: str) -> str:
    out = []
    for ch in s:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif 32 <= ord(ch) < 127:
            out.append(ch)
        else:
            for b in ch.encode("utf-8"):
                out.append(f"\\{b:03o}")
    return '"' + "".join(out) + '"'


def run_case(name: str, fn: str, spec_text: str, expected_keys: int) -> bool:
    print(f"\n===== [{name}] {spec_text} =====")
    cfg = HashConfig(mode="spec", key_type="string", func_name=fn,
                     key_spec=spec_text, expected_keys=expected_keys)
    b = generate(cfg)
    print("stats:", {k: v for k, v in b.stats.items()})
    for w in b.warnings:
        print("warn:", w)

    spec = parse_keyspec(spec_text)
    sim = simulate(spec, expected_keys, seed=1)
    keys = _sample_keys(spec, 300, 7)
    # 가변 길이 검증을 위해 짧은 키도 섞는다(스펙보다 짧게 잘라봄).
    extra = []
    for k in keys[:30]:
        if len(k) > spec.min_length:
            extra.append(k[: max(spec.min_length, len(k) - 2)])
    keys = keys + extra

    hfun = _ALGOS[sim.algorithm]
    rows = []
    for k in keys:
        idx = hfun(_processed_bytes(k, sim.offsets, sim.tail_start)) % sim.table_size
        rows.append((k, idx))

    arr = ",\n".join(f"    {{{_c_lit(k)}, {idx}u}}" for k, idx in rows)
    driver = f"""#include <stdio.h>
#include "{fn}.h"
struct row {{ const char *k; unsigned idx; }};
int main(void) {{
    struct row rows[] = {{
{arr}
    }};
    int n = sizeof(rows)/sizeof(rows[0]);
    int ok = 1;
    for (int i = 0; i < n; i++) {{
        unsigned got = {fn}(rows[i].k);
        if (got != rows[i].idx) {{
            printf("MISMATCH key=%s got=%u want=%u\\n", rows[i].k, got, rows[i].idx);
            ok = 0;
        }}
    }}
    printf(ok ? "OK matched=%d size=%d\\n" : "FAIL\\n", n, {fn.upper()}_TABLE_SIZE);
    return ok ? 0 : 1;
}}
"""
    with open(os.path.join(BUILD, f"{fn}.h"), "w", newline="\n") as f:
        f.write(b.header)
    with open(os.path.join(BUILD, f"{fn}.c"), "w", newline="\n") as f:
        f.write(b.source)
    dpath = os.path.join(BUILD, f"driver_{fn}.c")
    with open(dpath, "w", newline="\n") as f:
        f.write(driver)

    exe = os.path.join(BUILD, f"test_{fn}.exe")
    subprocess.run(["gcc", "-O2", "-Wall", "-Wextra", "-std=c11", "-I", BUILD,
                    os.path.join(BUILD, f"{fn}.c"), dpath, "-o", exe],
                   check=True, cwd=ROOT)
    res = subprocess.run([exe], capture_output=True, text=True)
    print("run:", res.stdout.strip() or res.stderr.strip())
    return res.returncode == 0


from core.spec_eval import packed_index  # noqa: E402  (C와 비트 일치 검증 대상)


def run_packed_case(name: str, fn: str, spec_text: str) -> bool:
    print(f"\n===== [{name}/packed] {spec_text} =====")
    cfg = HashConfig(mode="spec", key_type="string", func_name=fn, key_spec=spec_text)
    b = generate(cfg)
    print("stats:", {k: v for k, v in b.stats.items()})
    if not str(b.stats.get("strategy", "")).startswith("packed"):
        print("  EXPECTED packed-*, got", b.stats.get("strategy"))
        return False

    spec = parse_keyspec(spec_text)
    keys = _sample_keys(spec, 500, 7)
    rows = [(k, packed_index(spec, k)) for k in keys]
    # 단사(bijection) 확인: 서로 다른 키 → 서로 다른 인덱스
    if len({i for _, i in rows}) != len({k for k, _ in rows}):
        print("  python 단사성 실패")
        return False

    arr = ",\n".join(f"    {{{_c_lit(k)}, {idx}ull}}" for k, idx in rows)
    driver = f"""#include <stdio.h>
#include "{fn}.h"
struct row {{ const char *k; unsigned long long idx; }};
int main(void) {{
    struct row rows[] = {{
{arr}
    }};
    int n = sizeof(rows)/sizeof(rows[0]);
    int ok = 1;
    for (int i = 0; i < n; i++) {{
        unsigned long long got = (unsigned long long){fn}(rows[i].k);
        if (got != rows[i].idx) {{ printf("MISMATCH %s got=%llu want=%llu\\n",
            rows[i].k, got, rows[i].idx); ok = 0; }}
        if (got >= (unsigned long long){fn.upper()}_TABLE_SIZE) {{
            printf("OOB %s=%llu\\n", rows[i].k, got); ok=0; }}
    }}
    printf(ok ? "PACKED_OK matched=%d domain=%llu\\n" : "FAIL\\n",
           n, (unsigned long long){fn.upper()}_TABLE_SIZE);
    return ok ? 0 : 1;
}}
"""
    with open(os.path.join(BUILD, f"{fn}.h"), "w", newline="\n") as f:
        f.write(b.header)
    with open(os.path.join(BUILD, f"{fn}.c"), "w", newline="\n") as f:
        f.write(b.source)
    dpath = os.path.join(BUILD, f"driver_{fn}.c")
    with open(dpath, "w", newline="\n") as f:
        f.write(driver)
    exe = os.path.join(BUILD, f"test_{fn}.exe")
    subprocess.run(["gcc", "-O2", "-Wall", "-Wextra", "-std=c11", "-I", BUILD,
                    os.path.join(BUILD, f"{fn}.c"), dpath, "-o", exe], check=True, cwd=ROOT)
    res = subprocess.run([exe], capture_output=True, text=True)
    print("run:", res.stdout.strip() or res.stderr.strip())
    return res.returncode == 0


def main() -> int:
    os.makedirs(BUILD, exist_ok=True)
    try:
        subprocess.run(["gcc", "--version"], capture_output=True, check=True)
    except Exception:  # noqa: BLE001
        print("gcc 없음 — SKIP")
        return 0

    ok = True
    # 작은 도메인 → packed-dense (최소 완전 해시)
    ok &= run_packed_case("작은도메인", "phash", "[0]{0,2,[0~9]},[1]{2,3,[a~z]}")
    ok &= run_packed_case("숫자만", "nhash", "[0]{0,4,[0~9]}")
    ok &= run_packed_case("16진수", "xhash", "[0]{0,4,[0~9][a~f]}")
    # 큰 도메인(<2^64) → packed-wide (완전 해시, 64비트 인덱스)
    ok &= run_packed_case("큰도메인wide", "whash",
                          "[0]{0,4,[a~z][A~Z]},[1]{4,2,[0~9]},[2]{6,3,[a~z]}")
    # 가변 → byte-hash (완전 해시 아님)
    ok &= run_case("가변꼬리*", "vhash", "[0]{0,4,[a~z][A~Z]},[1]{4,*,[a~z][A~Z][0~9]}", 3000)
    ok &= run_case("가변범위", "rhash", "[0]{0,3,[A~Z]},[1]{3,2~8,[a~z]}", 1500)

    print()
    print("모든 spec 검증 통과." if ok else "일부 실패.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
