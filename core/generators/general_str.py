"""범용 문자열 해시 생성기: FNV-1a / DJB2 / SDBM."""
from __future__ import annotations

from .base import CodeBundle, Generator

# 본문은 32/64 공용으로 `h`(uint64_t)에 누적하고, 반환 시 캐스팅한다.
# 각 항목: (초기값식, 루프 본문). `c`는 현재 바이트(uint64_t로 승격됨).
_ALGOS = {
    "fnv1a": (
        "1469598103934665603ULL",  # 64bit FNV offset (32bit여도 동일 변수폭 사용)
        "        h ^= c;\n        h *= 1099511628211ULL;\n",
    ),
    "djb2": (
        "5381ULL",
        "        h = ((h << 5) + h) + c;  /* h*33 + c */\n",
    ),
    "sdbm": (
        "0ULL",
        "        h = c + (h << 6) + (h << 16) - h;\n",
    ),
}


class GeneralStringGenerator(Generator):
    def generate(self) -> CodeBundle:
        cfg = self.cfg
        fn = cfg.func_name
        ret_type = self._uint_type()
        prefix = cfg.macro_prefix
        init_expr, loop_body = _ALGOS[cfg.algorithm]

        # 시그니처: NUL종료 vs (ptr, len)
        if cfg.nul_terminated:
            signature = f"{ret_type} {fn}(const char *s)"
            loop_open = "    while (*s) {\n"
            byte_fetch = "        uint64_t c = (unsigned char)*s++;\n"
            loop_close = "    }\n"
        else:
            signature = f"{ret_type} {fn}(const void *key, size_t len)"
            loop_open = (
                "    const unsigned char *s = (const unsigned char *)key;\n"
                "    for (size_t i = 0; i < len; i++) {\n"
            )
            byte_fetch = "        uint64_t c = s[i];\n"
            loop_close = "    }\n"

        case_line = ""
        if cfg.case_insensitive:
            case_line = "        if (c >= 'A' && c <= 'Z') c += 32;  /* tolower */\n"

        seed_init = f" ^ {prefix}_SEED" if cfg.seed else ""

        cast = "(uint32_t)" if cfg.output_bits == 32 else ""
        ret_expr = f"{cast}h"
        if cfg.table_size is not None:
            ret_expr = f"({cast}h) % {prefix}_TABLE_SIZE"

        src = (
            f"{self._file_banner()}"
            f'#include "{fn}.h"\n\n'
            f"{signature} {{\n"
            f"    uint64_t h = {init_expr}{seed_init};\n"
            f"{loop_open}"
            f"{byte_fetch}"
            f"{case_line}"
            f"{loop_body}"
            f"{loop_close}"
            f"    return {ret_expr};\n"
            f"}}\n"
        )

        includes = "#include <stdint.h>\n"
        if not cfg.nul_terminated:
            includes += "#include <stddef.h>\n"

        defines = ""
        if cfg.seed:
            defines += f"#define {prefix}_SEED ((uint64_t){cfg.seed}u)\n"
        if cfg.table_size is not None:
            defines += f"#define {prefix}_TABLE_SIZE {cfg.table_size}u\n"
        if defines:
            defines += "\n"

        header = self._wrap_header(f"{defines}{signature};\n", includes=includes)

        return CodeBundle(
            header=header,
            source=src,
            stats={"algorithm": cfg.algorithm, "output_bits": cfg.output_bits},
        )
