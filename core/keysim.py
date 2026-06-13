"""구조 스펙 기반 해시 효율 시뮬레이션 (고정/가변 길이 지원).

목표: 키를 균일하게 분포시키면서 '가장 적은 바이트만' 처리하는 해시를 찾는다.

선택 단위
  - 고정 세그먼트의 개별 바이트(오프셋)
  - 가변 꼬리 세그먼트(있으면) 전체 — start..문자열끝 루프 1개 단위

근거
  1. 세그먼트별 엔트로피로 필요 임계값 산정 (birthday: >=2*log2(N)+margin, 또 >=log2(M))
  2. 엔트로피 밀도(=log2 카디널리티) 높은 단위부터 탐욕 선택해 임계값 충족
  3. 스펙을 따르는 합성 키 N개(가변 길이 포함)로 사전-해시 충돌 / %M 카이제곱 측정
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .hashers import MASK64
from .keyspec import KeySpec

_SAMPLE_CAP = 20000
_MARGIN_BITS = 8.0


def _fnv1a(byts: bytes) -> int:
    h = 2166136261
    for b in byts:
        h ^= b
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def _djb2(byts: bytes) -> int:
    h = 5381
    for b in byts:
        h = ((h * 33) + b) & 0xFFFFFFFF
    return h


_ALGOS = {"fnv1a": _fnv1a, "djb2": _djb2}


@dataclass
class SimResult:
    offsets: List[int]  # 선택된 고정 바이트 오프셋(정렬)
    tail_start: Optional[int]  # 가변 꼬리를 포함하면 그 시작 오프셋, 아니면 None
    variable: bool  # 경계 안전(가변 길이) 코드 필요 여부
    algorithm: str
    total_entropy: float
    selected_entropy: float
    threshold: float
    table_size: int  # M
    prehash_collisions: int
    chi_square: float
    dof: int
    sample_size: int
    bytes_per_key: float  # 평균 처리 바이트 (가변이면 기대값)
    full_bytes: int
    notes: List[str] = field(default_factory=list)

    @property
    def chi_norm(self) -> float:
        return self.chi_square / self.dof if self.dof else 0.0

    @property
    def speedup(self) -> float:
        return self.full_bytes / self.bytes_per_key if self.bytes_per_key else 1.0


def _table_size(expected_keys: int, load: float = 0.75) -> int:
    target = max(1, int(expected_keys / load))
    m = 1
    while m < target:
        m <<= 1
    return m


def _select(spec: KeySpec, threshold: float):
    """엔트로피 밀도 높은 단위부터 탐욕 선택.

    반환: (fixed_offsets[정렬], tail_start|None, selected_entropy)
    """
    items = []  # (density, entropy, kind, ref)
    for seg in spec.segments:
        if seg.cardinality <= 1:
            continue  # 정보 없는 고정 문자
        density = math.log2(seg.cardinality)
        if seg.variable:
            # 임계값에는 '보장' 엔트로피(min_len)만 반영 → 짧은 키도 구별되도록
            # 항상 존재하는 고정 접두부가 함께 선택된다(꼬리는 길수록 더 분산).
            guaranteed = seg.min_len * density
            items.append((density, guaranteed, "tail", seg.start))
        else:
            for off in seg.fixed_positions():
                items.append((density, density, "byte", off))
    # 밀도 내림차순, 동률이면 byte 먼저(지역성), 그다음 오프셋 순
    items.sort(key=lambda t: (-t[0], 0 if t[2] == "byte" else 1, t[3]))

    fixed: List[int] = []
    tail_start: Optional[int] = None
    acc = 0.0
    for density, entropy, kind, ref in items:
        if acc >= threshold:
            break
        if kind == "byte":
            fixed.append(ref)
        else:
            tail_start = ref
        acc += entropy
    fixed.sort()
    return fixed, tail_start, acc


def _selection_expected(spec: KeySpec, offsets, tail_start):
    """선택된 단위들의 기대 엔트로피와 평균 처리 바이트 수를 계산."""
    off_set = set(offsets)
    entropy = 0.0
    nbytes = float(len(offsets))
    for seg in spec.segments:
        if seg.variable or seg.cardinality <= 1:
            continue
        d = math.log2(seg.cardinality)
        for off in seg.fixed_positions():
            if off in off_set:
                entropy += d
    if tail_start is not None:
        tail = next(s for s in spec.segments if s.variable)
        entropy += tail.entropy_bits  # 기대 길이 기준
        nbytes += tail.expected_len
    return entropy, nbytes


def _sample_keys(spec: KeySpec, n: int, seed: int) -> List[str]:
    """스펙을 따르는 서로 다른 키 n개 (가변 꼬리는 길이도 무작위)."""
    state = (seed + 0x9E3779B9) & MASK64

    def nextr() -> int:
        nonlocal state
        state = (state * 6364136223846793005 + 1442695040888963407) & MASK64
        return state >> 33

    seg_chars = [sorted(s.charset) for s in spec.segments]
    out = set()
    attempts = 0
    max_attempts = n * 20 + 1000
    while len(out) < n and attempts < max_attempts:
        attempts += 1
        pieces = []
        for seg, chars in zip(spec.segments, seg_chars):
            length = seg.min_len
            if seg.variable and seg.max_len > seg.min_len:
                length = seg.min_len + nextr() % (seg.max_len - seg.min_len + 1)
            pieces.append("".join(chars[nextr() % len(chars)] for _ in range(length)))
        out.add("".join(pieces))
    return list(out)


def _processed_bytes(key: str, offsets: List[int], tail_start: Optional[int]) -> bytes:
    """C가 처리할 바이트열과 동일 순서: 고정 오프셋(오름차순, 길이 내) → 꼬리(start..끝)."""
    raw = key.encode("utf-8", "replace")
    n = len(raw)
    buf = bytearray(raw[o] for o in offsets if o < n)
    if tail_start is not None:
        buf.extend(raw[tail_start:n])
    return bytes(buf)


def evaluate(keys, offsets, tail_start, algo, m) -> Tuple[int, float]:
    hfun = _ALGOS[algo]
    buckets = [0] * m
    seen = set()
    prehash = 0
    for k in keys:
        pb = _processed_bytes(k, offsets, tail_start)
        if pb in seen:
            prehash += 1
        else:
            seen.add(pb)
        buckets[hfun(pb) % m] += 1
    mean = len(keys) / m
    chi = sum((c - mean) ** 2 for c in buckets) / mean if mean > 0 else 0.0
    return prehash, chi


def simulate(spec: KeySpec, expected_keys: int, seed: int = 1) -> SimResult:
    n = max(2, min(expected_keys, _SAMPLE_CAP))
    m = _table_size(expected_keys)

    threshold = max(2 * math.log2(max(2, expected_keys)) + _MARGIN_BITS, math.log2(m) + 4)
    threshold = min(threshold, spec.total_entropy_bits)

    offsets, tail_start, _guaranteed = _select(spec, threshold)
    if not offsets and tail_start is None:
        # 모두 고정 문자 — 구분 불가. 안전망으로 첫 세그먼트라도 처리.
        if spec.segments:
            offsets = list(spec.segments[0].fixed_positions())

    keys = _sample_keys(spec, n, seed)
    dof = m - 1

    best = None
    for algo in _ALGOS:
        pre, chi = evaluate(keys, offsets, tail_start, algo, m)
        score = abs(chi / dof - 1.0) if dof else 0.0
        cand = (score, pre, chi, algo)
        if best is None or cand < best:
            best = cand
    _, prehash, chi, algo = best

    # 선택의 기대 엔트로피(가변 꼬리는 기대 길이 기준) + 평균 처리 바이트
    sel_entropy, bytes_per_key = _selection_expected(spec, offsets, tail_start)

    notes = []
    if sel_entropy < threshold - 1e-9:
        notes.append(
            f"선택 엔트로피({sel_entropy:.1f}b)가 임계값({threshold:.1f}b)보다 낮습니다. "
            f"스펙의 가용 엔트로피가 부족하거나 키가 충분히 구별되지 않을 수 있습니다.")
    if prehash > 0:
        notes.append(
            f"샘플에서 사전-해시 충돌 {prehash}건: 선택 바이트만으로 일부 키가 같아집니다.")
    if spec.has_variable:
        notes.append(
            "가변 길이 스펙: 생성 코드는 strlen 기반 경계 검사로 짧은 키에도 안전합니다.")

    return SimResult(
        offsets=offsets, tail_start=tail_start, variable=spec.has_variable,
        algorithm=algo, total_entropy=spec.total_entropy_bits,
        selected_entropy=sel_entropy, threshold=threshold, table_size=m,
        prehash_collisions=prehash, chi_square=chi, dof=dof,
        sample_size=len(keys), bytes_per_key=bytes_per_key,
        full_bytes=spec.total_length, notes=notes,
    )


def group_ranges(offsets: List[int]) -> List[Tuple[int, int]]:
    """정렬된 오프셋을 연속 구간 [(start, length), ...] 으로 묶는다."""
    ranges = []
    for off in offsets:
        if ranges and off == ranges[-1][0] + ranges[-1][1]:
            s, ln = ranges[-1]
            ranges[-1] = (s, ln + 1)
        else:
            ranges.append((off, 1))
    return ranges
