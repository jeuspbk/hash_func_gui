"""생성기 추상 기반 클래스 및 산출물 자료형."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List

from ..config import HashConfig


@dataclass
class CodeBundle:
    header: str  # .h 내용
    source: str  # .c 내용
    stats: Dict = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


class Generator(ABC):
    def __init__(self, cfg: HashConfig):
        self.cfg = cfg

    @abstractmethod
    def generate(self) -> CodeBundle:  # pragma: no cover - 추상
        ...

    # --- 하위 클래스 공용 헬퍼 ---
    def _uint_type(self) -> str:
        return "uint32_t" if self.cfg.output_bits == 32 else "uint64_t"

    def _header_guard(self) -> str:
        return f"{self.cfg.macro_prefix}_H"

    def _file_banner(self) -> str:
        return (
            "/* 이 파일은 hash_func_gen 으로 자동 생성되었습니다. 직접 수정하지 마세요. */\n"
        )

    def _wrap_header(self, body: str, includes: str = "#include <stdint.h>\n") -> str:
        guard = self._header_guard()
        return (
            f"{self._file_banner()}"
            f"#ifndef {guard}\n#define {guard}\n\n"
            f"{includes}\n"
            f"{body}\n"
            f"#endif /* {guard} */\n"
        )
