"""생성기 팩토리: (mode, key_type) 조합으로 적절한 Generator를 선택."""
from __future__ import annotations

from ..config import HashConfig
from .base import CodeBundle, Generator
from .general_int import GeneralIntGenerator
from .general_str import GeneralStringGenerator
from .perfect_int import PerfectIntGenerator
from .perfect_str import PerfectStringGenerator
from .spec_str import SpecStringGenerator

_REGISTRY = {
    ("general", "int"): GeneralIntGenerator,
    ("general", "string"): GeneralStringGenerator,
    ("perfect", "int"): PerfectIntGenerator,
    ("perfect", "string"): PerfectStringGenerator,
    ("spec", "string"): SpecStringGenerator,
}


def select_generator(cfg: HashConfig) -> Generator:
    try:
        cls = _REGISTRY[(cfg.mode, cfg.key_type)]
    except KeyError:
        raise ValueError(f"지원하지 않는 조합: mode={cfg.mode}, key_type={cfg.key_type}")
    return cls(cfg)


def generate(cfg: HashConfig) -> CodeBundle:
    """검증 후 코드 생성까지 한 번에. GUI/CLI 공통 진입점."""
    from ..validators import validate

    warnings = validate(cfg)
    bundle = select_generator(cfg).generate()
    bundle.warnings = warnings + bundle.warnings
    return bundle


__all__ = ["select_generator", "generate", "CodeBundle", "Generator"]
