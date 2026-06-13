"""파이썬측 참조 해시 구현.

여기 정의된 base_hash는 perfect 생성기가 방출하는 C 코드의 base hash와
'비트 단위로 동일'해야 한다. (탐색/검증을 파이썬에서 하고 결과 테이블만 C로 방출)
"""
from __future__ import annotations

MASK64 = (1 << 64) - 1


def base_hash_string(s: str, seed: int, case_insensitive: bool = False) -> int:
    """seed를 섞은 FNV-1a 64. C 코드와 동일하게 바이트 단위(UTF-8) 처리."""
    if case_insensitive:
        s = s.lower()
    data = s.encode("utf-8")
    h = (1469598103934665603 ^ (seed & MASK64)) & MASK64
    for b in data:
        h ^= b
        h = (h * 1099511628211) & MASK64
    return h


def base_hash_int(x: int, seed: int) -> int:
    """seed를 더한 뒤 SplitMix64 mix. C 코드와 동일."""
    x = (x + (seed & MASK64)) & MASK64
    x ^= x >> 33
    x = (x * 0xFF51AFD7ED558CCD) & MASK64
    x ^= x >> 33
    x = (x * 0xC4CEB9FE1A85EC53) & MASK64
    x ^= x >> 33
    return x


def base_hash(key, seed: int, *, key_type: str, case_insensitive: bool = False) -> int:
    if key_type == "string":
        return base_hash_string(key, seed, case_insensitive)
    return base_hash_int(int(key), seed)
