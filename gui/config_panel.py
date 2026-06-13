"""좌측 설정 패널: 위젯 값을 HashConfig로 직렬화한다."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from core.config import GENERAL_ALGORITHMS, HashConfig

# 문자종류 프리셋: (표시 라벨, 스펙 토큰). 길이 칸은 N / a~b / * 를 직접 입력.
# 콤보박스는 편집 가능하므로 프리셋 외에 사용자 정의 토큰(예: [0~9][a~f], [!~/])도 입력 가능.
CHARCLASS_PRESETS = [
    ("영문자(대소)", "[a~z][A~Z]"),
    ("소문자", "[a~z]"),
    ("대문자", "[A~Z]"),
    ("숫자", "[0~9]"),
    ("영숫자", "[a~z][A~Z][0~9]"),
    ("16진수(소)", "[0~9][a~f]"),
    ("16진수(대)", "[0~9][A~F]"),
]
_LABEL_TO_TOKEN = {label: token for label, token in CHARCLASS_PRESETS}
_TOKEN_TO_LABEL = {token: label for label, token in CHARCLASS_PRESETS}
_CHARCLASS_LABELS = [label for label, _ in CHARCLASS_PRESETS]


class ConfigPanel(ttk.Frame):
    def __init__(self, master, on_change: Callable[[], None]):
        super().__init__(master, padding=8)
        self._on_change = on_change
        self._build()
        self._sync_enabled()

    # --- 위젯 구성 ---
    def _build(self) -> None:
        self.mode = tk.StringVar(value="general")
        self.key_type = tk.StringVar(value="string")
        self.func_name = tk.StringVar(value="myhash")
        self.output_bits = tk.IntVar(value=32)
        self.algorithm = tk.StringVar(value="fnv1a")
        self.seed = tk.StringVar(value="0")
        self.table_size = tk.StringVar(value="")
        self.int_width = tk.IntVar(value=64)
        self.case_insensitive = tk.BooleanVar(value=False)
        self.nul_terminated = tk.BooleanVar(value=True)
        self.minimal = tk.BooleanVar(value=True)
        self.emit_verify = tk.BooleanVar(value=False)
        self.expected_keys = tk.StringVar(value="1000")
        self.pack_max = tk.StringVar(value="4194304")
        self.test_input = tk.StringVar(value="")
        self.prime_input = tk.StringVar(value="")

        row = 0

        def label(text):
            nonlocal row
            ttk.Label(self, text=text).grid(row=row, column=0, sticky="w", pady=2)

        # 모드
        label("모드")
        f = ttk.Frame(self); f.grid(row=row, column=1, sticky="w"); row += 1
        for val, txt in (("general", "범용"), ("perfect", "Perfect"), ("spec", "구조분석")):
            ttk.Radiobutton(f, text=txt, value=val, variable=self.mode,
                            command=self._on_mode).pack(side="left")

        # 키 타입
        label("키 타입")
        f = ttk.Frame(self); f.grid(row=row, column=1, sticky="w"); row += 1
        self.keytype_radios = []
        for val, txt in (("string", "문자열"), ("int", "정수")):
            rb = ttk.Radiobutton(f, text=txt, value=val, variable=self.key_type,
                                 command=self._on_keytype)
            rb.pack(side="left")
            self.keytype_radios.append(rb)

        # 함수 이름
        label("함수 이름")
        ttk.Entry(self, textvariable=self.func_name).grid(
            row=row, column=1, sticky="ew"); row += 1
        self.func_name.trace_add("write", lambda *_: self._changed())

        # 알고리즘
        label("알고리즘")
        self.algo_combo = ttk.Combobox(self, textvariable=self.algorithm,
                                       state="readonly", values=GENERAL_ALGORITHMS["string"])
        self.algo_combo.grid(row=row, column=1, sticky="ew"); row += 1
        self.algo_combo.bind("<<ComboboxSelected>>", lambda *_: self._changed())

        # 출력 폭
        label("출력 폭")
        f = ttk.Frame(self); f.grid(row=row, column=1, sticky="w"); row += 1
        for val in (32, 64):
            ttk.Radiobutton(f, text=f"{val}bit", value=val, variable=self.output_bits,
                            command=self._changed).pack(side="left")

        # 정수 폭
        self.intwidth_label = ttk.Label(self, text="정수 인자 폭")
        self.intwidth_label.grid(row=row, column=0, sticky="w")
        self.intwidth_frame = ttk.Frame(self); self.intwidth_frame.grid(
            row=row, column=1, sticky="w"); row += 1
        for val in (32, 64):
            ttk.Radiobutton(self.intwidth_frame, text=f"{val}bit", value=val,
                            variable=self.int_width, command=self._changed).pack(side="left")

        # 시드
        label("시드")
        e = ttk.Entry(self, textvariable=self.seed); e.grid(row=row, column=1, sticky="ew")
        row += 1
        self.seed.trace_add("write", lambda *_: self._changed())

        # TABLE_SIZE (general 전용)
        self.tablesize_label = ttk.Label(self, text="TABLE_SIZE (선택)")
        self.tablesize_label.grid(row=row, column=0, sticky="w")
        self.tablesize_entry = ttk.Entry(self, textvariable=self.table_size)
        self.tablesize_entry.grid(row=row, column=1, sticky="ew"); row += 1
        self.table_size.trace_add("write", lambda *_: self._changed())

        # 문자열 옵션
        self.ci_check = ttk.Checkbutton(self, text="대소문자 무시",
                                        variable=self.case_insensitive, command=self._changed)
        self.ci_check.grid(row=row, column=1, sticky="w"); row += 1
        self.nul_check = ttk.Checkbutton(self, text="NUL 종료 (해제 시 ptr+len)",
                                         variable=self.nul_terminated, command=self._changed)
        self.nul_check.grid(row=row, column=1, sticky="w"); row += 1

        # perfect 옵션
        self.minimal_check = ttk.Checkbutton(self, text="최소 완전 해시(minimal)",
                                             variable=self.minimal, command=self._changed)
        self.minimal_check.grid(row=row, column=1, sticky="w"); row += 1
        self.verify_check = ttk.Checkbutton(self, text="검증 테이블/lookup 방출",
                                            variable=self.emit_verify, command=self._changed)
        self.verify_check.grid(row=row, column=1, sticky="w"); row += 1

        # perfect 키 목록
        self.keys_label = ttk.Label(self, text="키 목록 (한 줄에 하나)")
        self.keys_label.grid(row=row, column=0, sticky="nw")
        self.keys_text = tk.Text(self, height=6, width=28)
        self.keys_text.grid(row=row, column=1, sticky="ew"); row += 1
        self.keys_text.bind("<KeyRelease>", lambda *_: self._changed())

        # spec(구조분석): 예상 키 개수
        self.expkeys_label = ttk.Label(self, text="예상 키 개수")
        self.expkeys_label.grid(row=row, column=0, sticky="w")
        self.expkeys_entry = ttk.Entry(self, textvariable=self.expected_keys)
        self.expkeys_entry.grid(row=row, column=1, sticky="ew"); row += 1
        self.expected_keys.trace_add("write", lambda *_: self._changed())

        # spec(구조분석): 패킹 한계 도메인 (이하면 혼합 진법 직접 인덱싱 자동 선택)
        self.packmax_label = ttk.Label(self, text="패킹 한계 도메인")
        self.packmax_label.grid(row=row, column=0, sticky="w")
        self.packmax_entry = ttk.Entry(self, textvariable=self.pack_max)
        self.packmax_entry.grid(row=row, column=1, sticky="ew"); row += 1
        self.pack_max.trace_add("write", lambda *_: self._changed())

        # spec(구조분석): 세그먼트 행 편집기
        self.spec_label = ttk.Label(self, text="세그먼트")
        self.spec_label.grid(row=row, column=0, sticky="nw")
        self.seg_container = ttk.Frame(self)
        self.seg_container.grid(row=row, column=1, sticky="ew"); row += 1
        self.seg_rows = []  # [{start, len, type, widgets:[...]}]
        self.add_seg_btn = ttk.Button(self, text="+ 세그먼트 추가",
                                      command=lambda: self._add_segment_row())
        self.add_seg_btn.grid(row=row, column=1, sticky="w"); row += 1
        self.spec_hint = ttk.Label(
            self, foreground="#666", wraplength=300, justify="left",
            text=("길이: N(고정) / a~b · *(가변, 마지막만)\n"
                  "문자종류: 프리셋 선택 또는 직접 입력 (예: [0~9][a~f], [!~/])"))
        self.spec_hint.grid(row=row, column=1, sticky="w"); row += 1

        # spec(구조분석): 테스트 입력 → 해시값 미리보기
        self.test_label = ttk.Label(self, text="테스트 입력")
        self.test_label.grid(row=row, column=0, sticky="w")
        self.test_entry = ttk.Entry(self, textvariable=self.test_input)
        self.test_entry.grid(row=row, column=1, sticky="ew"); row += 1
        self.test_input.trace_add("write", lambda *_: self._update_test())
        self.test_result = ttk.Label(self, foreground="#063", wraplength=300,
                                     justify="left", text="")
        self.test_result.grid(row=row, column=1, sticky="w"); row += 1

        # 초기 세그먼트 2개
        self._add_segment_row(0, "4", "[a~z][A~Z]")
        self._add_segment_row(4, "2", "[0~9]")

        # 유틸리티: 다음 소수 (모드 무관, 항상 사용 가능 — 예: 소수 테이블 크기 선택)
        ttk.Separator(self, orient="horizontal").grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=6); row += 1
        ttk.Label(self, text="유틸리티: 다음 소수").grid(row=row, column=0, sticky="w")
        self.prime_entry = ttk.Entry(self, textvariable=self.prime_input)
        self.prime_entry.grid(row=row, column=1, sticky="ew"); row += 1
        self.prime_input.trace_add("write", lambda *_: self._update_prime())
        self.prime_result = ttk.Label(self, foreground="#063", wraplength=300,
                                      justify="left", text="숫자를 입력하면 그보다 큰 첫 소수를 표시합니다.")
        self.prime_result.grid(row=row, column=1, sticky="w"); row += 1

        self.columnconfigure(1, weight=1)

    # --- 이벤트 ---
    def _changed(self) -> None:
        self._sync_enabled()
        self._update_test()
        self._on_change()

    def _update_test(self) -> None:
        """테스트 입력 키에 대한 해시값을 계산해 표시 (spec 모드에서만)."""
        if not hasattr(self, "test_result"):
            return
        if self.mode.get() != "spec":
            self.test_result.configure(text="")
            return
        key = self.test_input.get()
        if not key:
            self.test_result.configure(text="키를 입력하면 해시값이 표시됩니다.")
            return
        try:
            from core.spec_eval import spec_hash
            value, strategy, size = spec_hash(self.build_config(), key)
            self.test_result.configure(
                foreground="#063",
                text=f"→ {value}  ({strategy}, 0..{size - 1})")
        except Exception as exc:  # noqa: BLE001
            self.test_result.configure(foreground="#a40", text=f"계산 불가: {exc}")

    def _update_prime(self) -> None:
        """입력 숫자보다 큰 첫 소수를 계산해 표시 (모드 무관)."""
        text = self.prime_input.get().strip()
        if not text:
            self.prime_result.configure(
                foreground="#063", text="숫자를 입력하면 그보다 큰 첫 소수를 표시합니다.")
            return
        try:
            n = int(text, 0)
        except ValueError:
            self.prime_result.configure(foreground="#a40", text="정수를 입력하세요.")
            return
        from core.primes import next_prime
        p = next_prime(n)
        self.prime_result.configure(foreground="#063", text=f"→ {p}  (> {n})")

    def _on_mode(self) -> None:
        # 구조분석(spec)은 문자열 전용 → 키 타입 고정
        if self.mode.get() == "spec":
            self.key_type.set("string")
            self._on_keytype()
            return
        self._changed()

    # --- 세그먼트 행 편집기 ---
    def _add_segment_row(self, start=None, length="1", charclass=None) -> None:
        if start is None:
            start = self._next_start()
        label = _TOKEN_TO_LABEL.get(charclass, charclass) if charclass else _CHARCLASS_LABELS[0]
        if label not in _CHARCLASS_LABELS:
            label = _CHARCLASS_LABELS[0]
        rd = {
            "start": tk.StringVar(value=str(start)),
            "len": tk.StringVar(value=str(length)),
            "type": tk.StringVar(value=label),
        }
        rd["start"].trace_add("write", lambda *_: self._changed())
        rd["len"].trace_add("write", lambda *_: self._changed())
        rd["type"].trace_add("write", lambda *_: self._changed())
        self.seg_rows.append(rd)
        self._render_segments()
        self._changed()

    def _remove_segment_row(self, rd) -> None:
        if rd in self.seg_rows:
            self.seg_rows.remove(rd)
        self._render_segments()
        self._changed()

    def _next_start(self) -> int:
        """마지막 세그먼트의 시작+길이를 다음 시작값으로 추정(가변/비정수는 0)."""
        if not self.seg_rows:
            return 0
        last = self.seg_rows[-1]
        try:
            return int(last["start"].get(), 0) + int(last["len"].get(), 0)
        except ValueError:
            return 0

    def _render_segments(self) -> None:
        for child in self.seg_container.winfo_children():
            child.destroy()
        hdr = ("시작", "길이", "문자종류", "")
        for c, t in enumerate(hdr):
            ttk.Label(self.seg_container, text=t, foreground="#666").grid(
                row=0, column=c, padx=1, sticky="w")
        for i, rd in enumerate(self.seg_rows, start=1):
            ttk.Entry(self.seg_container, textvariable=rd["start"], width=5).grid(
                row=i, column=0, padx=1, pady=1)
            ttk.Entry(self.seg_container, textvariable=rd["len"], width=5).grid(
                row=i, column=1, padx=1, pady=1)
            # state="normal" → 프리셋 선택 + 사용자 정의 토큰 직접 입력 모두 가능
            ttk.Combobox(self.seg_container, textvariable=rd["type"], width=14,
                         state="normal", values=_CHARCLASS_LABELS).grid(
                row=i, column=2, padx=1, pady=1)
            ttk.Button(self.seg_container, text="✕", width=2,
                       command=lambda r=rd: self._remove_segment_row(r)).grid(
                row=i, column=3, padx=1, pady=1)

    def _segment_spec_text(self) -> str:
        parts = []
        for i, rd in enumerate(self.seg_rows):
            start = rd["start"].get().strip()
            length = rd["len"].get().strip()
            token = _LABEL_TO_TOKEN.get(rd["type"].get(), rd["type"].get())
            parts.append(f"[{i}]{{{start},{length},{token}}}")
        return ",".join(parts)

    def set_segments(self, rows) -> None:
        """테스트/프로그램 설정용: rows = [(start, length, token_or_label), ...]."""
        self.seg_rows = []
        for start, length, cc in rows:
            self._add_segment_row(start, str(length), cc)

    def _on_keytype(self) -> None:
        kt = self.key_type.get()
        algos = GENERAL_ALGORITHMS[kt]
        self.algo_combo["values"] = algos
        if self.algorithm.get() not in algos:
            self.algorithm.set(algos[0])
        self._changed()

    def _sync_enabled(self) -> None:
        mode = self.mode.get()
        is_general = mode == "general"
        is_perfect = mode == "perfect"
        is_spec = mode == "spec"
        is_int = self.key_type.get() == "int"
        is_str = not is_int

        def show(widget, visible):
            widget.configure(state="normal" if visible else "disabled")

        # spec은 문자열 전용 → 키 타입 라디오 잠금
        for rb in self.keytype_radios:
            show(rb, not is_spec)

        # 알고리즘/TABLE_SIZE은 general에서만 (spec은 알고리즘 자동 선택)
        self.algo_combo.configure(state="readonly" if is_general else "disabled")
        show(self.tablesize_entry, is_general)
        # 정수 폭은 정수 키일 때만 (ttk.Frame은 state 옵션이 없으므로 자식만 토글)
        for child in self.intwidth_frame.winfo_children():
            show(child, is_int and not is_spec)
        # 문자열 옵션 (spec에서는 무관)
        show(self.ci_check, is_str and not is_spec)
        show(self.nul_check, is_str and is_general)  # ptr+len은 범용에서만
        # perfect 옵션/키목록
        show(self.minimal_check, is_perfect)
        show(self.verify_check, is_perfect)
        self.keys_text.configure(state="normal" if is_perfect else "disabled")
        # spec 위젯: 세그먼트 편집기/개수 필드는 항상 편집 가능(spec 모드에서만 사용)
        show(self.expkeys_entry, True)

    # --- 직렬화 ---
    def build_config(self) -> HashConfig:
        seed = _safe_int(self.seed.get(), 0)
        table_size = _safe_int(self.table_size.get(), None)
        keys = self._parse_keys()
        return HashConfig(
            mode=self.mode.get(),
            key_type=self.key_type.get(),
            func_name=self.func_name.get().strip() or "myhash",
            output_bits=self.output_bits.get(),
            algorithm=self.algorithm.get(),
            seed=seed,
            table_size=table_size,
            int_width=self.int_width.get(),
            case_insensitive=self.case_insensitive.get(),
            nul_terminated=self.nul_terminated.get(),
            keys=keys,
            minimal=self.minimal.get(),
            emit_verify_table=self.emit_verify.get(),
            key_spec=self._segment_spec_text(),
            expected_keys=_safe_int(self.expected_keys.get(), 1000) or 1000,
            pack_max_domain=_safe_int(self.pack_max.get(), 1 << 22) or (1 << 22),
        )

    def _parse_keys(self) -> list:
        raw = self.keys_text.get("1.0", "end").splitlines()
        lines = [ln.strip() for ln in raw if ln.strip()]
        if self.key_type.get() == "int":
            out = []
            for ln in lines:
                v = _safe_int(ln, None)
                if v is not None:
                    out.append(v)
            return out
        return lines


def _safe_int(text: str, default) -> Optional[int]:
    text = (text or "").strip()
    if not text:
        return default
    try:
        return int(text, 0)
    except ValueError:
        return default
