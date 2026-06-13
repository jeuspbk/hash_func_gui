"""범용 정수 해시 생성기: SplitMix64 / Thomas Wang / Knuth 곱셈 해시.

모든 알고리즘은 64bit 누적 변수 `h` 위에서 동작하고, 마지막에 출력 폭으로
캐스팅(+선택적 모듈로)하여 반환한다.
"""
from __future__ import annotations

from .base import CodeBundle, Generator

# 각 알고리즘 본문. 64bit 변수 `h`를 in-place로 변형한다.
_BODIES = {
    "splitmix": (
        "    h ^= h >> 33;  h *= 0xff51afd7ed558ccdULL;\n"
        "    h ^= h >> 33;  h *= 0xc4ceb9fe1a85ec53ULL;\n"
        "    h ^= h >> 33;\n"
    ),
    "wang": (
        "    h = (~h) + (h << 21);\n"
        "    h = h ^ (h >> 24);\n"
        "    h = (h + (h << 3)) + (h << 8);\n"
        "    h = h ^ (h >> 14);\n"
        "    h = (h + (h << 2)) + (h << 4);\n"
        "    h = h ^ (h >> 28);\n"
        "    h = h + (h << 31);\n"
    ),
    "knuth": (
        "    h *= 0x9e3779b97f4a7c15ULL;  /* 2^64 / phi */\n"
    ),
}


class GeneralIntGenerator(Generator):
    def generate(self) -> CodeBundle:
        cfg = self.cfg
        fn = cfg.func_name
        ret_type = self._uint_type()
        arg_type = "uint32_t" if cfg.int_width == 32 else "uint64_t"
        prefix = cfg.macro_prefix

        seed_line = f"    h += {prefix}_SEED;\n" if cfg.seed else ""

        cast = "(uint32_t)" if cfg.output_bits == 32 else ""
        ret_expr = f"{cast}h"
        if cfg.table_size is not None:
            ret_expr = f"({cast}h) % {prefix}_TABLE_SIZE"

        signature = f"{ret_type} {fn}({arg_type} key)"

        src = (
            f"{self._file_banner()}"
            f'#include "{fn}.h"\n\n'
            f"{signature} {{\n"
            f"    uint64_t h = (uint64_t)key;\n"
            f"{seed_line}"
            f"{_BODIES[cfg.algorithm]}"
            f"    return {ret_expr};\n"
            f"}}\n"
        )

        defines = ""
        if cfg.seed:
            defines += f"#define {prefix}_SEED ((uint64_t){cfg.seed}u)\n"
        if cfg.table_size is not None:
            defines += f"#define {prefix}_TABLE_SIZE {cfg.table_size}u\n"
        if defines:
            defines += "\n"

        header = self._wrap_header(f"{defines}{signature};\n")

        return CodeBundle(
            header=header,
            source=src,
            stats={"algorithm": cfg.algorithm, "output_bits": cfg.output_bits},
        )
