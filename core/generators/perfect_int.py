"""정수 키 집합에 대한 Perfect Hash 생성기."""
from __future__ import annotations

from .perfect_common import PerfectGeneratorBase


class PerfectIntGenerator(PerfectGeneratorBase):
    def _arg_signature(self) -> str:
        return "uint64_t key"

    def _verify_ctype(self) -> str:
        return "uint64_t"

    def _key_literal(self, key) -> str:
        return f"{int(key)}ULL"

    def _compare_expr(self, arr_elem: str) -> str:
        return f"{arr_elem} == key"

    def _empty_literal(self) -> str:
        # 비최소 모드의 빈 슬롯 센티넬. 키가 이 값과 같으면 오탐 가능(드묾).
        return "0xFFFFFFFFFFFFFFFFULL"

    def _is_empty_expr(self, arr_elem: str) -> str:
        return f"{arr_elem} == 0xFFFFFFFFFFFFFFFFULL"
