"""Hash Function Generator 진입점.

GUI 실행:   python main.py
CLI 자가검증: python main.py --selftest
"""
from __future__ import annotations

import sys


def _selftest() -> int:
    """핵심 생성기 스모크 테스트 (Tkinter 없이 동작)."""
    from core.config import HashConfig
    from core.generators import generate

    cases = [
        HashConfig(mode="general", key_type="string", algorithm="fnv1a"),
        HashConfig(mode="general", key_type="int", algorithm="splitmix", seed=42),
        HashConfig(mode="perfect", key_type="string",
                   keys=["apple", "banana", "cherry", "date", "fig", "grape"],
                   emit_verify_table=True),
        HashConfig(mode="perfect", key_type="int",
                   keys=[10, 20, 33, 47, 1000, 99999]),
    ]
    for cfg in cases:
        bundle = generate(cfg)
        tag = f"{cfg.mode}/{cfg.key_type}/{cfg.algorithm}"
        assert "#ifndef" in bundle.header, tag
        assert cfg.func_name in bundle.source, tag
        if cfg.mode == "perfect":
            assert bundle.stats.get("collisions") == 0, tag
        print(f"[OK] {tag:28} stats={bundle.stats}")
        for w in bundle.warnings:
            print(f"     warn: {w}")
    print("\n자가검증 통과.")
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return _selftest()
    from gui.app import main as gui_main
    gui_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
