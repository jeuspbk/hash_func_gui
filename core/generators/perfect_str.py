"""문자열 키 집합에 대한 Perfect Hash 생성기."""
from __future__ import annotations

from .perfect_common import PerfectGeneratorBase

_ESCAPE = {
    "\\": "\\\\",
    '"': '\\"',
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}


def _c_string_literal(s: str) -> str:
    out = []
    for ch in s:
        if ch in _ESCAPE:
            out.append(_ESCAPE[ch])
        elif 32 <= ord(ch) < 127:
            out.append(ch)
        else:
            # UTF-8 바이트를 8진 이스케이프로 (이식성)
            for b in ch.encode("utf-8"):
                out.append(f"\\{b:03o}")
    return '"' + "".join(out) + '"'


class PerfectStringGenerator(PerfectGeneratorBase):
    def _arg_signature(self) -> str:
        return "const char *key"

    def _verify_ctype(self) -> str:
        return "char *"

    def _key_literal(self, key) -> str:
        return _c_string_literal(str(key))

    def _compare_expr(self, arr_elem: str) -> str:
        return f"strcmp({arr_elem}, key) == 0"

    def _empty_literal(self) -> str:
        return "0"  # null 포인터 상수

    def _is_empty_expr(self, arr_elem: str) -> str:
        return f"!{arr_elem}"

    def _verify_extra_includes(self) -> str:
        return "#include <string.h>\n"
