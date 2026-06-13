"""생성된 C 코드를 실제로 컴파일/실행하여 검증하는 통합 테스트.

gcc 가 PATH 에 있어야 한다. 없으면 SKIP.
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
BUILD = os.path.join(ROOT, "build")

from core.config import HashConfig  # noqa: E402
from core.generators import generate  # noqa: E402


def _write(name: str, content: str) -> str:
    path = os.path.join(BUILD, name)
    with open(path, "w", newline="\n", encoding="utf-8") as f:
        f.write(content)
    return path


def _compile_run(sources, exe, include=BUILD) -> str:
    out = os.path.join(BUILD, exe)
    cmd = ["gcc", "-O2", "-Wall", "-Wextra", "-std=c11", "-I", include,
           *sources, "-o", out]
    subprocess.run(cmd, check=True, cwd=ROOT)
    res = subprocess.run([out], check=True, capture_output=True, text=True)
    return res.stdout.strip()


def check_perfect_string() -> None:
    keys = ["apple", "banana", "cherry", "date", "fig", "grape", "kiwi", "lemon"]
    cfg = HashConfig(mode="perfect", key_type="string", func_name="phash",
                     keys=keys, emit_verify_table=True)
    b = generate(cfg)
    _write("phash.h", b.header)
    csrc = _write("phash.c", b.source)

    keys_c = ", ".join(f'"{k}"' for k in keys)
    driver = f"""#include <stdio.h>
#include "phash.h"
int main(void) {{
    const char *keys[] = {{ {keys_c} }};
    int n = {len(keys)};
    int seen[PHASH_SIZE]; for (int i=0;i<PHASH_SIZE;i++) seen[i]=-1;
    int ok=1;
    for (int i=0;i<n;i++) {{
        unsigned h = phash(keys[i]);
        if (h>=PHASH_SIZE) {{ printf("OOB %s\\n", keys[i]); ok=0; continue; }}
        if (seen[h]!=-1) {{ printf("COLLISION %s/%s\\n", keys[seen[h]], keys[i]); ok=0; }}
        seen[h]=i;
        if (phash_lookup(keys[i])!=(int)h) {{ printf("lookup-mismatch %s\\n", keys[i]); ok=0; }}
    }}
    if (phash_lookup("nope")!=-1) {{ printf("false-positive\\n"); ok=0; }}
    printf(ok?"PERFECT_OK size=%d\\n":"FAIL\\n", PHASH_SIZE);
    return ok?0:1;
}}
"""
    dsrc = _write("driver_str.c", driver)
    print("perfect/string:", _compile_run([csrc, dsrc], "test_str.exe"))


def check_perfect_int() -> None:
    keys = [10, 20, 33, 47, 1000, 99999, 7, 8]
    cfg = HashConfig(mode="perfect", key_type="int", func_name="ihash", keys=keys)
    b = generate(cfg)
    _write("ihash.h", b.header)
    csrc = _write("ihash.c", b.source)
    keys_c = ", ".join(f"{k}ULL" for k in keys)
    driver = f"""#include <stdio.h>
#include <stdint.h>
#include "ihash.h"
int main(void) {{
    uint64_t keys[] = {{ {keys_c} }};
    int n = {len(keys)};
    int seen[IHASH_SIZE]; for (int i=0;i<IHASH_SIZE;i++) seen[i]=-1;
    int ok=1;
    for (int i=0;i<n;i++) {{
        unsigned h = ihash(keys[i]);
        if (h>=IHASH_SIZE || seen[h]!=-1) {{ printf("FAIL key=%llu\\n",(unsigned long long)keys[i]); ok=0; }}
        else seen[h]=i;
    }}
    printf(ok?"PERFECT_OK size=%d\\n":"FAIL\\n", IHASH_SIZE);
    return ok?0:1;
}}
"""
    dsrc = _write("driver_int.c", driver)
    print("perfect/int:   ", _compile_run([csrc, dsrc], "test_int.exe"))


def check_general() -> None:
    """범용 해시는 컴파일만 확인."""
    for kt, algo in (("string", "fnv1a"), ("int", "splitmix")):
        cfg = HashConfig(mode="general", key_type=kt, func_name="ghash",
                         algorithm=algo, seed=7, table_size=256)
        b = generate(cfg)
        _write("ghash.h", b.header)
        csrc = _write("ghash.c", b.source)
        stub = '#include "ghash.h"\nint main(void){return 0;}\n'
        dsrc = _write("driver_g.c", stub)
        _compile_run([csrc, dsrc], "test_g.exe")
        print(f"general/{kt}/{algo}: compile OK")


def main() -> int:
    os.makedirs(BUILD, exist_ok=True)
    try:
        subprocess.run(["gcc", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("gcc 없음 — SKIP")
        return 0
    check_general()
    check_perfect_string()
    check_perfect_int()
    print("\n모든 컴파일/실행 검증 통과.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
