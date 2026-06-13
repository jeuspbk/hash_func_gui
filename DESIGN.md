# Hash Function Generator — 설계 문서

GUI에서 **키 타입**과 **키 구성/파라미터**를 입력받아 **C 언어 해시 함수 소스(.h/.c)** 를 생성하는 데스크톱 도구.

## 1. 목표와 범위

| 항목 | 결정 |
|------|------|
| GUI 기술 | Python 3.10+ / Tkinter (표준 라이브러리만 사용) |
| 해시 종류 | (A) 범용 해시(General) + (B) Perfect Hash 둘 다 |
| 키 타입 | 정수형(`uint32_t`/`uint64_t` 등), 문자열(`char*`) |
| 출력 | C 헤더(.h) + 소스(.c), 미리보기/저장/복사 |
| 외부 의존성 | 없음 (Tkinter, dataclasses, string.Template 등 표준만) |

비범위(추후 확장): 바이트 배열/복합 구조체 키, 암호학적 해시, jinja 등 외부 템플릿 엔진.

## 2. 두 가지 해시 모드

### (A) 범용 해시 — General
임의의 키 입력에 대해 잘 분산되는 해시값을 만든다. 키 집합을 미리 몰라도 됨.

- **정수 키**: SplitMix64 / Murmur 3 finalizer(권장 기본), Thomas Wang, Knuth 곱셈 해시(Fibonacci hashing)
- **문자열 키**: FNV-1a(권장 기본), DJB2, SDBM, MurmurHash3(x86_32)

파라미터: 출력 폭(32/64bit), 시드, (선택) `% TABLE_SIZE` 모듈로 방출, 문자열의 경우 대소문자 무시 / NUL종료 vs `(ptr,len)`.

### (B) Perfect Hash — 고정 키 집합
사용자가 키 목록을 입력하면, 그 키들에 대해 **충돌 없는**(가능하면 minimal: 0..n-1) 해시를 생성.

- **알고리즘(권장, 구현 단순)**: *시드 탐색식 2단계 해시 (CHD-lite)*
  - 1차: `bucket = base_hash(key, seed0) % r` 로 키를 버킷에 분배 (r ≈ n)
  - 2차: 버킷마다 `displacement[bucket]` 시드를 0,1,2…로 증가시키며 탐색하여
    `slot = base_hash(key, displacement[bucket]) % m` 이 비어있도록 배치
  - 결과물: `displacement[]` 테이블 + (minimal일 때) 재배치 인덱스 테이블
  - 소규모(~수천 키)에서 빠르고 결정적. 실패 시 r/m/seed0 자동 재시도.
- **간이 대안**(키 수십 개 이하): 단일 시드 brute-force — `base_hash(key) ^ seed` 가 단사(injective)가 되는 seed를 0..N 탐색.
- 생성 시 **검증 단계**: 모든 키를 실제로 돌려 충돌 0건 확인, 미해결 시 GUI에 리포트.
- 미지의 키 처리 옵션: 인덱스 범위 클램프 / 키 검증 테이블 동시 생성(`strcmp` 확인용).

## 3. 디렉토리 구조

```
hash_func_gen/
├── main.py                      # 엔트리포인트: GUI 실행
├── core/
│   ├── config.py                # HashConfig 등 dataclass (GUI⇄생성기 계약)
│   ├── validators.py            # 입력 검증 (함수명, 시드, 키 중복 등)
│   ├── hashers.py               # 파이썬측 참조 해시 구현 (perfect 탐색/검증용)
│   └── generators/
│       ├── base.py              # Generator ABC, CodeBundle(header, source, stats)
│       ├── general_int.py
│       ├── general_str.py
│       ├── perfect_int.py
│       └── perfect_str.py
├── templates/                   # string.Template 기반 C 코드 골격
│   ├── header.h.tmpl
│   ├── general_int.c.tmpl
│   ├── general_str.c.tmpl
│   └── perfect.c.tmpl
├── gui/
│   ├── app.py                   # 메인 윈도우 / 레이아웃 / 이벤트 배선
│   ├── config_panel.py          # 좌측 설정 패널 (모드·키타입·파라미터·키목록 편집)
│   └── preview_panel.py         # 우측 코드 미리보기(.h/.c 탭) + 통계/리포트
├── tests/
│   ├── test_generators.py       # 생성 C코드 골든 비교, 컴파일 가능성
│   └── test_perfect.py          # 충돌 0건 검증
└── DESIGN.md
```

## 4. 데이터 모델 (`core/config.py`)

```python
from dataclasses import dataclass, field
from typing import Literal, Optional

@dataclass
class HashConfig:
    mode: Literal["general", "perfect"] = "general"
    key_type: Literal["int", "string"] = "string"
    func_name: str = "myhash"
    output_bits: Literal[32, 64] = 32

    # general 공통
    algorithm: str = "fnv1a"          # 키타입별 허용값 다름
    seed: int = 0
    table_size: Optional[int] = None  # 설정 시 결과에 % TABLE_SIZE 적용

    # 정수 키
    int_width: Literal[32, 64] = 64

    # 문자열 키
    case_insensitive: bool = False
    nul_terminated: bool = True       # False면 (const void*, size_t len) 시그니처

    # perfect 전용
    keys: list = field(default_factory=list)  # 고정 키 목록(int 또는 str)
    minimal: bool = True
    emit_verify_table: bool = False   # 미지 키 구분용 원본 키 테이블 방출
```

GUI는 위젯 값을 `HashConfig`로 직렬화 → 생성기에 전달. 생성기는 GUI를 모른다(테스트 용이).

## 5. 생성기 인터페이스 (`core/generators/base.py`)

```python
@dataclass
class CodeBundle:
    header: str            # .h 내용
    source: str            # .c 내용
    stats: dict            # {"collisions":0, "table_size":n, "load":..., "tries":k}
    warnings: list[str]

class Generator(ABC):
    def __init__(self, cfg: HashConfig): ...
    @abstractmethod
    def generate(self) -> CodeBundle: ...
```

팩토리: `select_generator(cfg)` 가 `(mode, key_type)` 조합으로 4개 구현 중 하나 반환.

## 6. 생성 코드 예시

**범용 정수 (SplitMix64 finalizer → 32bit):**
```c
uint32_t myhash(uint64_t key) {
    key ^= key >> 33;  key *= 0xff51afd7ed558ccdULL;
    key ^= key >> 33;  key *= 0xc4ceb9fe1a85ec53ULL;
    key ^= key >> 33;
    return (uint32_t)key;          /* table_size 설정 시: % MYHASH_TABLE_SIZE */
}
```

**범용 문자열 (FNV-1a 32):**
```c
uint32_t myhash(const char *s) {
    uint32_t h = 2166136261u ^ MYHASH_SEED;
    while (*s) { h ^= (unsigned char)*s++; h *= 16777619u; }
    return h;
}
```

**Perfect (문자열, CHD-lite):** `displacement[]`, (minimal 시) `index[]` 테이블 + 조회 함수, 옵션으로 `keys[]` 검증 테이블 방출.

## 7. GUI 레이아웃 (Tkinter)

```
┌──────────────────────────────────────────────────────────┐
│  [범용 ○ / Perfect ○]   키타입: [정수 ○ / 문자열 ○]        │  ← 모드 바
├────────────────────────┬─────────────────────────────────┤
│  설정 패널 (config)     │  미리보기 (preview)              │
│  · 함수 이름            │  ┌ .h ┬ .c ┐                     │
│  · 알고리즘 ▼           │  │  생성된 C 코드 (읽기전용)      │
│  · 출력폭 32/64         │  │                               │
│  · 시드 / TABLE_SIZE    │  └───────────────────────────────│
│  · (문자열) 대소문자/길이│  통계: 충돌 0 / 테이블 n / 시도 k │
│  · (perfect) 키 목록    │                                  │
│    편집기(추가/삭제/임포트)│                                 │
├────────────────────────┴─────────────────────────────────┤
│           [생성]  [.h 저장] [.c 저장] [클립보드 복사]       │
└──────────────────────────────────────────────────────────┘
```

- 설정 변경 → 디바운스(~300ms) 후 자동 재생성하여 미리보기 갱신.
- Perfect 모드: 키 목록 편집기(여러 줄 텍스트 또는 리스트박스), 파일에서 줄단위 임포트.
- 키타입/모드에 따라 무관한 위젯은 비활성/숨김(상태 머신).
- 검증 실패·중복 키 등은 미리보기 하단 리포트 영역에 경고로 표시.

## 8. 처리 흐름

```
위젯 입력 → HashConfig 직렬화 → validators 검증
   → select_generator(cfg).generate() → CodeBundle
   → preview(.h/.c) + stats 갱신 → [저장/복사]
```

Perfect 탐색은 키가 많을 때 수백 ms~초 걸릴 수 있으므로 **백그라운드 스레드**에서 실행하고 GUI에는 진행/완료만 통지(Tkinter는 `after`로 메인스레드 갱신).

## 9. 구현 단계 (제안)

1. `core/config.py` + `validators.py` + `base.py` 골격
2. 범용 생성기 2종(int/str) + 템플릿 → CLI로 stdout 출력 검증
3. Tkinter 최소 GUI(범용만) 배선 + 미리보기/저장
4. Perfect 생성기(str → int) + 충돌 검증 + 백그라운드 실행
5. 키 목록 편집기/임포트, 경고 리포트 UI
6. `tests/`: 골든 출력 비교, gcc 컴파일 스모크 테스트, 충돌 0건 검증

## 10. 열린 질문

- Perfect 모드에서 **정수 키 집합**도 문자열과 동일 UI로 받을지(쉼표/줄 구분 파싱).
- 생성 C 코드에 라이선스/주석 헤더를 넣을지, 인덴트·네이밍 컨벤션 옵션 제공 여부.
- minimal perfect hash 외에 "비최소(빈 슬롯 허용, 더 빠른 생성)" 옵션 노출 여부.
