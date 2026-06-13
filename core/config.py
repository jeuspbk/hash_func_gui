"""HashConfig: GUI와 생성기 사이의 계약(데이터 모델).

GUI는 위젯 값을 HashConfig로 직렬화하여 생성기에 넘기고,
생성기는 GUI를 전혀 알지 못한다(테스트/CLI에서 독립 실행 가능).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Literal, Optional

Mode = Literal["general", "perfect", "spec"]
KeyType = Literal["int", "string"]

# 키타입별 허용 범용 알고리즘. GUI 드롭다운도 이 표를 참조한다.
GENERAL_ALGORITHMS = {
    "int": ["splitmix", "wang", "knuth"],
    "string": ["fnv1a", "djb2", "sdbm"],
}


@dataclass
class HashConfig:
    mode: Mode = "general"
    key_type: KeyType = "string"
    func_name: str = "myhash"
    output_bits: Literal[32, 64] = 32

    # --- general 공통 ---
    algorithm: str = "fnv1a"
    seed: int = 0
    table_size: Optional[int] = None  # 설정 시 결과에 % TABLE_SIZE 적용

    # --- 정수 키 ---
    int_width: Literal[32, 64] = 64

    # --- 문자열 키 ---
    case_insensitive: bool = False
    nul_terminated: bool = True  # False면 (const void*, size_t len) 시그니처

    # --- perfect 전용 ---
    keys: List = field(default_factory=list)  # 고정 키 목록 (int 또는 str)
    minimal: bool = True
    emit_verify_table: bool = False  # 미지 키 구분용 원본 키 테이블 방출

    # --- spec(구조분석) 전용 ---
    key_spec: str = ""  # 예: [0]{0,4,[a~z][A~Z]},[1]{4,2,[0~9]}
    expected_keys: int = 1000  # 시뮬레이션/테이블 크기 산정용 예상 키 개수
    # 패킹 도메인(=세그먼트 카디널리티 곱)이 이 값 이하이면 혼합 진법 직접
    # 인덱싱(완전 해시, 충돌 0)을 자동 선택. 그보다 크면 바이트 해시로 폴백.
    pack_max_domain: int = 1 << 22  # 약 419만

    @property
    def macro_prefix(self) -> str:
        """생성 코드의 매크로/상수 접두사 (예: MYHASH)."""
        return self.func_name.strip().upper() or "MYHASH"

    def default_algorithm(self) -> str:
        return GENERAL_ALGORITHMS[self.key_type][0]
