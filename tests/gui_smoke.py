"""GUI 헤드리스 스모크 테스트.

mainloop() 대신 update()로 이벤트 루프를 수동으로 펌프하며,
실제 위젯 배선(설정 변경 → 디바운스 → 백그라운드 생성 → 미리보기 갱신)이
동작하는지 확인한다. 시각적 창 상호작용 없이 내용 검증.
"""
from __future__ import annotations

import os
import sys
import time

# 콘솔이 cp949 등일 때 ✖/⚠ 같은 기호 출력으로 죽지 않도록.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def pump(app, seconds: float) -> None:
    """주어진 시간 동안 Tk 이벤트(after 콜백 포함)를 처리."""
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.02)


def read_preview(app):
    h = app.preview_panel.header_text.get("1.0", "end").strip()
    c = app.preview_panel.source_text.get("1.0", "end").strip()
    stats = app.preview_panel.stats_var.get()
    warn = app.preview_panel.warn_var.get()
    return h, c, stats, warn


def main() -> int:
    try:
        from gui.app import App
        app = App()
    except Exception as exc:  # noqa: BLE001 - 디스플레이 없음 등
        print(f"GUI 생성 불가(헤드리스 환경?): {type(exc).__name__}: {exc}")
        return 2

    failures = []

    # 1) 초기 상태(범용/문자열/fnv1a) — 초기 schedule_regenerate가 채워야 함
    pump(app, 1.0)
    h, c, stats, warn = read_preview(app)
    print("[1] 범용/문자열 초기 생성")
    print("    stats:", stats)
    if "#ifndef MYHASH_H" not in h or "myhash" not in c:
        failures.append("초기 범용 생성 실패")
    else:
        print("    OK: 헤더/소스 생성됨")

    # 2) 범용 → 정수, 알고리즘 splitmix, 64bit
    app.config_panel.key_type.set("int")
    app.config_panel._on_keytype()
    app.config_panel.output_bits.set(64)
    app.config_panel.seed.set("123")
    app.config_panel._changed()
    pump(app, 1.0)
    h, c, stats, warn = read_preview(app)
    print("[2] 범용/정수/splitmix/64bit/seed=123")
    print("    stats:", stats)
    if "uint64_t myhash(uint64_t key)" not in c or "MYHASH_SEED" not in h:
        failures.append("정수 모드 생성 실패")
    else:
        print("    OK: 정수 시그니처+시드 매크로 확인")

    # 3) Perfect/문자열 + 키 목록 + 검증 테이블
    app.config_panel.mode.set("perfect")
    app.config_panel.key_type.set("string")
    app.config_panel._on_keytype()
    app.config_panel.emit_verify.set(True)
    app.config_panel.keys_text.configure(state="normal")
    app.config_panel.keys_text.delete("1.0", "end")
    app.config_panel.keys_text.insert("1.0", "alpha\nbeta\ngamma\ndelta\nepsilon\nzeta\n")
    app.config_panel._changed()
    pump(app, 1.5)
    h, c, stats, warn = read_preview(app)
    print("[3] Perfect/문자열 6키 + 검증테이블")
    print("    stats:", stats)
    if "myhash_lookup" not in c or "myhash_disp" not in c or "collisions=0" not in stats:
        failures.append("Perfect 모드 생성 실패")
    else:
        print("    OK: disp/rank/lookup 테이블 + 충돌 0")

    # 3.5) 구조분석(spec) 모드
    app.config_panel.func_name.set("shash")
    app.config_panel.mode.set("spec")
    app.config_panel._on_mode()
    app.config_panel.set_segments([(0, 4, "[a~z][A~Z]"), (4, 2, "[0~9]")])
    app.config_panel.expected_keys.set("2000")
    app.config_panel._changed()
    pump(app, 1.5)
    h, c, stats, warn = read_preview(app)
    print("[3.5] 구조분석(spec) 모드")
    print("    stats:", stats)
    if "Structure-driven" not in c or "TABLE_SIZE" not in h or "strategy=" not in stats:
        failures.append("spec 모드 생성 실패")
    else:
        print("    OK: 구조기반 효율 해시 생성 (근거 주석 포함)")
    app.config_panel.func_name.set("myhash")
    app.config_panel.mode.set("general")
    app.config_panel._on_mode()

    # 4) 잘못된 함수 이름 → 오류 표시
    app.config_panel.func_name.set("9bad")
    app.config_panel._changed()
    pump(app, 1.0)
    h, c, stats, warn = read_preview(app)
    print("[4] 잘못된 식별자 입력")
    print("    warn:", warn)
    if "✖" not in warn:
        failures.append("검증 오류가 미리보기에 표시되지 않음")
    else:
        print("    OK: 오류 메시지 표시")

    app.destroy()

    print()
    if failures:
        print("실패:", failures)
        return 1
    print("GUI 스모크 테스트 통과 (4/4).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
