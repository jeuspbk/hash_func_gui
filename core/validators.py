"""HashConfig 입력 검증. 생성 전에 호출하여 사용자 입력 오류를 잡는다."""
from __future__ import annotations

import re
from typing import List

from .config import GENERAL_ALGORITHMS, HashConfig

_C_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ValidationError(Exception):
    """검증 실패. 메시지는 GUI 리포트 영역에 그대로 표시 가능."""


def validate(cfg: HashConfig) -> List[str]:
    """치명적 오류는 ValidationError로 raise, 비치명적은 경고 리스트로 반환."""
    warnings: List[str] = []

    if not _C_IDENT.match(cfg.func_name.strip()):
        raise ValidationError(
            f"함수 이름 '{cfg.func_name}'이(가) 올바른 C 식별자가 아닙니다."
        )

    if cfg.output_bits not in (32, 64):
        raise ValidationError("출력 폭은 32 또는 64여야 합니다.")

    if cfg.mode == "general":
        allowed = GENERAL_ALGORITHMS[cfg.key_type]
        if cfg.algorithm not in allowed:
            raise ValidationError(
                f"'{cfg.key_type}' 키에는 {allowed} 알고리즘만 사용할 수 있습니다."
            )
        if cfg.table_size is not None and cfg.table_size <= 0:
            raise ValidationError("TABLE_SIZE는 양의 정수여야 합니다.")

    if cfg.mode == "perfect":
        _validate_perfect_keys(cfg)

    if cfg.mode == "spec":
        if cfg.key_type != "string":
            raise ValidationError("구조분석(spec) 모드는 문자열 키에서만 사용할 수 있습니다.")
        from .keyspec import KeySpecError, parse_keyspec
        try:
            spec = parse_keyspec(cfg.key_spec)
        except KeySpecError as e:
            raise ValidationError(str(e))
        if cfg.expected_keys is not None and cfg.expected_keys <= 1:
            warnings.append("예상 키 개수가 너무 작습니다(>=2 권장).")
        if spec.total_entropy_bits <= 0:
            raise ValidationError("모든 세그먼트가 고정 문자라 키를 구분할 수 없습니다.")

    if cfg.seed < 0:
        warnings.append("시드가 음수입니다. unsigned로 캐스팅되어 사용됩니다.")

    return warnings


def _validate_perfect_keys(cfg: HashConfig) -> None:
    keys = cfg.keys
    if not keys:
        raise ValidationError("Perfect 모드에서는 키 목록이 비어 있을 수 없습니다.")

    if len(set(_normalize(k, cfg) for k in keys)) != len(keys):
        raise ValidationError("키 목록에 중복(또는 대소문자 무시 시 충돌)이 있습니다.")

    if cfg.key_type == "int":
        for k in keys:
            if not isinstance(k, int):
                raise ValidationError(f"정수 키가 아닙니다: {k!r}")


def _normalize(key, cfg: HashConfig):
    if cfg.key_type == "string" and cfg.case_insensitive and isinstance(key, str):
        return key.lower()
    return key
