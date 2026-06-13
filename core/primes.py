"""소수 유틸리티.

is_prime: 결정적 Miller-Rabin. witness 집합 {2,3,5,...,37} 은 n < 3.3e24 에서
정확하므로 64비트 범위(및 그 이상 상당 구간)에서 오판 없음.
next_prime: 입력보다 '큰' 첫 소수.
"""
from __future__ import annotations

_WITNESSES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)


def is_prime(n: int) -> bool:
    if n < 2:
        return False
    for p in _WITNESSES:
        if n % p == 0:
            return n == p
    d = n - 1
    r = 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for a in _WITNESSES:
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(r - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def next_prime(n: int) -> int:
    """n 보다 '큰' 첫 소수 (strictly greater)."""
    if n < 2:
        return 2
    c = n + 1
    if c % 2 == 0:
        c += 1
    while not is_prime(c):
        c += 2
    return c
