# Hash Function Generator

GUI에서 **키 타입**(정수/문자열)과 **구성**을 입력받아 **C 해시 함수(.h/.c)** 를 생성하는 도구.
범용 해시(General)와 완전 해시(Perfect) 두 모드를 지원한다. 설계 상세는 [`DESIGN.md`](DESIGN.md).

저장소: <https://github.com/jeuspbk/hash_func_gui>

```bash
git clone https://github.com/jeuspbk/hash_func_gui.git
```

## 실행

```bash
python main.py             # GUI 실행 (Tkinter, 표준 라이브러리만)
python main.py --selftest  # GUI 없이 핵심 생성기 자가검증
```

Windows에서는 배치 파일로 더블클릭 실행도 가능합니다:

```
run.bat          # 콘솔 창과 함께 실행 (오류 시 메시지 유지)
run_silent.bat   # pythonw로 콘솔 없이 GUI만 실행
```

## 구조

```
core/                생성 로직 (GUI 비의존, 단독 import/테스트 가능)
  config.py          HashConfig — GUI↔생성기 계약
  validators.py      입력 검증
  hashers.py         파이썬측 참조 해시 (perfect 탐색/검증; C와 비트 동일)
  generators/        general_int / general_str / perfect_int / perfect_str
gui/                 Tkinter UI (config_panel · preview_panel · app)
tests/compile_check.py  생성 C코드를 gcc로 컴파일·실행하여 충돌 0 검증
main.py              진입점
```

## 모드 요약

- **범용(General)**
  - 정수: `splitmix` / `wang` / `knuth`
  - 문자열: `fnv1a` / `djb2` / `sdbm`
  - 옵션: 출력 32/64bit, 시드, `% TABLE_SIZE`, (문자열) 대소문자 무시 · NUL종료/`ptr+len`
- **Perfect** (고정 키 집합, 충돌 0 보장)
  - CHD-lite(hash-and-displace)로 부하율 ~0.5에서 안정 탐색, `minimal` 시 rank로 0..n-1 압축
  - 옵션: `minimal`, 검증 테이블/`<fn>_lookup` 방출(미지 키 구분)
  - 성능 참고: 문자열 1000키 기준 수 ms 내 생성
- **구조분석(spec)** (문자열 키의 구조로부터 해시 자동 생성)
  - 입력: 세그먼트 행 편집기(시작/길이/문자종류) — 문자종류는 프리셋 또는 직접 입력
  - 길이 토큰: `N`(고정), `a~b`/`*`(가변, 마지막 세그먼트만)
  - **기본 목표는 완전 해시(충돌 0)**. 구조만으로 만드는 완전 해시 = 혼합 진법 패킹.
    비둘기집 원리상 완전 해시의 테이블 크기 = 패킹 도메인(카디널리티 곱)이다.
  - 전략 자동 선택:
    - `packed-dense` : 도메인 ≤ `pack_max`(그리고 ≤ 2³²) → 최소 완전 해시(uint32), 반환값=인덱스
    - `packed-wide`  : 도메인 < 2⁶⁴ → 완전 해시(uint64 고유 인덱스, 희소)
    - `byte-hash`    : 도메인 ≥ 2⁶⁴ 또는 가변 길이 → **완전 해시 불가**, 일반 균일 해시로 폴백(경고)
  - 충돌 0이 꼭 필요한데 도메인이 너무 크면: 고정 길이/작은 스펙으로 줄이거나, 실제 키 목록으로 **Perfect 모드** 사용
  - **테스트 입력란**: 키를 넣으면 해시값을 즉시 표시(숫자/16진수 전용은 입력=출력)
  - C↔Python 비트 일치 검증(`core/spec_eval.py`, `tests/spec_check.py`)

## 검증 (gcc 필요)

```bash
python tests/compile_check.py
```
생성된 코드를 실제 컴파일하고, 모든 키가 충돌 없이 유일 슬롯에 매핑되는지(+`lookup` 정확도, 오탐 없음) 확인한다.
