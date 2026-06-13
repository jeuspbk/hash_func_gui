"""spec 모드 해시의 Python 평가기.

생성된 C 코드와 '비트 단위로 동일한' 결과를 내야 한다(테스트로 검증).
GUI 테스트 입력란과 통합 테스트가 공용으로 사용한다. 생성기(spec_str)의
전략 선택 분기와 동일한 조건을 따른다.
"""
from __future__ import annotations

from .config import HashConfig
from .keysim import _ALGOS, _processed_bytes, simulate
from .keyspec import KeySpec, parse_keyspec


def packed_index(spec: KeySpec, key: str) -> int:
    """혼합 진법 직접 인덱싱 (packed-index)와 동일."""
    idx = 0
    for seg in spec.packable_segments():
        chars = sorted(seg.charset)
        rank = {c: i for i, c in enumerate(chars)}
        for off in range(seg.start, seg.start + seg.min_len):
            ch = key[off] if off < len(key) else ""
            idx = idx * seg.cardinality + rank.get(ch, 0)
    return idx


def spec_hash(cfg: HashConfig, key: str):
    """현재 설정으로 생성될 해시 함수가 key에 대해 내는 값.

    반환: (value, strategy, table_size)
    """
    spec = parse_keyspec(cfg.key_spec)
    pack_max = cfg.pack_max_domain or (1 << 22)
    domain = spec.packing_domain()
    if domain is not None and domain > 1:
        if domain <= min(pack_max, 1 << 32):
            return packed_index(spec, key), "packed-dense", domain
        if domain < (1 << 64):
            return packed_index(spec, key), "packed-wide", domain

    sim = simulate(spec, max(2, cfg.expected_keys or 1000), seed=cfg.seed or 1)
    pb = _processed_bytes(key, sim.offsets, sim.tail_start)
    value = _ALGOS[sim.algorithm](pb) % sim.table_size
    return value, "byte-hash", sim.table_size
