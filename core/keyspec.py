"""문자열 키의 '구조 스펙' 파서 (고정/가변 길이 지원).

입력 형식 (세그먼트 나열):
    [0]{start_offset,length,charclasses},[1]{start_offset,length,charclasses}, ...

length 토큰:
    N        : 고정 길이 N 바이트
    a~b      : 가변, a..b 바이트 (마지막 세그먼트만 허용)
    *        : 가변, 1..기본상한 바이트, 문자열 끝까지 (마지막 세그먼트만 허용)

예:
    [0]{0,4,[a~z][A~Z]},[1]{4,2,[0~9]}              # 고정 6바이트
    [0]{0,4,[a~z][A~Z]},[1]{4,*,[a~z][A~Z][0~9]}     # 4바이트 접두 + 가변 꼬리

charclasses 토큰:
    [x~y]  : x..y 범위 (예: [a~z], [A~Z], [0~9])
    그 외 대괄호 밖 문자는 리터럴로 취급
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import List

_SEG_RE = re.compile(r"\{([^}]*)\}")
_RANGE_RE = re.compile(r"\[([^\]])~([^\]])\]")

_STAR_DEFAULT_MAX = 16  # '*' 가변 꼬리의 샘플링/엔트로피용 기본 상한
_STAR_DEFAULT_MIN = 1


class KeySpecError(Exception):
    """구조 스펙 파싱/검증 실패."""


@dataclass
class Segment:
    start: int  # 바이트 오프셋
    min_len: int
    max_len: int
    variable: bool
    charset: frozenset  # 허용 문자 집합 (샘플링용)
    label: str  # 표시용 원본 문자클래스 텍스트

    @property
    def cardinality(self) -> int:
        return len(self.charset)

    @property
    def expected_len(self) -> float:
        return (self.min_len + self.max_len) / 2 if self.variable else self.min_len

    @property
    def entropy_bits(self) -> float:
        """기여 엔트로피(비트). 고정 문자(카디널리티 1)는 0."""
        if self.cardinality <= 1:
            return 0.0
        return self.expected_len * math.log2(self.cardinality)

    def fixed_positions(self) -> range:
        """고정 길이 세그먼트의 바이트 오프셋. 가변 세그먼트엔 의미 없음."""
        if self.variable:
            return range(0)
        return range(self.start, self.start + self.min_len)

    def length_label(self) -> str:
        if not self.variable:
            return str(self.min_len)
        if self.max_len >= _STAR_DEFAULT_MAX and self.min_len <= _STAR_DEFAULT_MIN:
            return "*"
        return f"{self.min_len}~{self.max_len}"


@dataclass
class KeySpec:
    segments: List[Segment]

    @property
    def has_variable(self) -> bool:
        return any(s.variable for s in self.segments)

    @property
    def tail_start(self):
        """가변 꼬리 세그먼트의 시작 오프셋(없으면 None)."""
        for s in self.segments:
            if s.variable:
                return s.start
        return None

    @property
    def total_length(self) -> int:
        """최대 가능 길이 (버퍼/오프셋 상한)."""
        return max((s.start + s.max_len for s in self.segments), default=0)

    @property
    def min_length(self) -> int:
        return max((s.start + s.min_len for s in self.segments), default=0)

    @property
    def total_entropy_bits(self) -> float:
        return sum(s.entropy_bits for s in self.segments)

    def packing_domain(self):
        """혼합 진법으로 패킹했을 때의 도메인 크기(=구별 가능한 키 수).

        가변 세그먼트가 있으면 무한 → None. 정보 없는 고정 문자(카디널리티 1)는
        곱에 1로 기여(영향 없음).
        """
        if self.has_variable:
            return None
        domain = 1
        for s in self.segments:
            if s.cardinality > 1:
                domain *= s.cardinality ** s.min_len
        return domain

    def packable_segments(self) -> List[Segment]:
        """패킹에 기여하는(카디널리티>1) 세그먼트들."""
        return [s for s in self.segments if s.cardinality > 1 and not s.variable]


def _parse_charset(text: str):
    chars = set()
    label_parts = []
    for m in _RANGE_RE.finditer(text):
        lo, hi = ord(m.group(1)), ord(m.group(2))
        if hi < lo:
            lo, hi = hi, lo
        chars.update(chr(c) for c in range(lo, hi + 1))
        label_parts.append(f"[{m.group(1)}~{m.group(2)}]")
    leftover = _RANGE_RE.sub("", text)
    for ch in leftover:
        if not ch.isspace():
            chars.add(ch)
            label_parts.append(ch)
    if not chars:
        raise KeySpecError(f"문자클래스를 해석할 수 없습니다: {text!r}")
    return frozenset(chars), "".join(label_parts)


def _parse_length(tok: str):
    """(min_len, max_len, variable) 반환."""
    tok = tok.strip()
    if tok == "*":
        return _STAR_DEFAULT_MIN, _STAR_DEFAULT_MAX, True
    if "~" in tok:
        lo_s, hi_s = tok.split("~", 1)
        try:
            lo, hi = int(lo_s.strip(), 0), int(hi_s.strip(), 0)
        except ValueError:
            raise KeySpecError(f"가변 길이 범위 형식 오류: {tok!r}")
        if lo < 0 or hi < lo:
            raise KeySpecError(f"가변 길이 범위가 올바르지 않습니다: {tok!r}")
        return lo, hi, True
    try:
        n = int(tok, 0)
    except ValueError:
        raise KeySpecError(f"length가 정수/범위/'*'가 아닙니다: {tok!r}")
    if n <= 0:
        raise KeySpecError(f"length는 양수여야 합니다: {tok!r}")
    return n, n, False


def parse_keyspec(text: str) -> KeySpec:
    bodies = _SEG_RE.findall(text or "")
    if not bodies:
        raise KeySpecError(
            "구조 스펙을 찾을 수 없습니다. 예: [0]{0,4,[a~z][A~Z]},[1]{4,2,[0~9]}"
        )
    segments: List[Segment] = []
    for body in bodies:
        parts = body.split(",", 2)
        if len(parts) < 3:
            raise KeySpecError(f"세그먼트 형식 오류 {{ {body} }} — start,length,charclass 필요")
        try:
            start = int(parts[0].strip(), 0)
        except ValueError:
            raise KeySpecError(f"start가 정수가 아닙니다: {{ {body} }}")
        min_len, max_len, variable = _parse_length(parts[1])
        charset, label = _parse_charset(parts[2])
        segments.append(Segment(start, min_len, max_len, variable, charset, label))

    segments.sort(key=lambda s: s.start)
    _validate(segments)
    return KeySpec(segments)


def _validate(segments: List[Segment]) -> None:
    var_count = sum(1 for s in segments if s.variable)
    if var_count > 1:
        raise KeySpecError("가변 길이 세그먼트는 하나만 허용됩니다.")
    if var_count == 1 and not segments[-1].variable:
        raise KeySpecError("가변 길이 세그먼트는 마지막에 와야 합니다.")
    prev_end = -1
    for s in segments[:-1] if segments else []:
        if s.variable:
            raise KeySpecError("가변 길이 세그먼트는 마지막에 와야 합니다.")
        if s.start < prev_end:
            raise KeySpecError(
                f"세그먼트가 겹칩니다 (offset {s.start} < 이전 끝 {prev_end})."
            )
        prev_end = s.start + s.max_len
    if segments and segments[-1].start < prev_end:
        raise KeySpecError(
            f"세그먼트가 겹칩니다 (offset {segments[-1].start} < 이전 끝 {prev_end})."
        )
