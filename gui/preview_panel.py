"""우측 미리보기 패널: .h / .c 탭 + 통계/경고."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from core.generators import CodeBundle


class PreviewPanel(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=8)
        self._build()

    def _build(self) -> None:
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)

        self.header_text = self._make_code_tab(nb, "헤더 (.h)")
        self.source_text = self._make_code_tab(nb, "소스 (.c)")

        self.stats_var = tk.StringVar(value="대기 중…")
        ttk.Label(self, textvariable=self.stats_var, foreground="#226").pack(
            anchor="w", pady=(6, 0))

        self.warn_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.warn_var, foreground="#a40",
                  wraplength=520, justify="left").pack(anchor="w")

    def _make_code_tab(self, nb, title) -> tk.Text:
        frame = ttk.Frame(nb)
        nb.add(frame, text=title)
        text = tk.Text(frame, wrap="none", font=("Consolas", 10))
        yscroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        xscroll = ttk.Scrollbar(frame, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set,
                       state="disabled")
        text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        return text

    # --- 갱신 ---
    def show_bundle(self, bundle: CodeBundle) -> None:
        self._set_text(self.header_text, bundle.header)
        self._set_text(self.source_text, bundle.source)
        stats = "  ".join(f"{k}={v}" for k, v in bundle.stats.items())
        self.stats_var.set(stats or "생성 완료")
        self.warn_var.set("\n".join(f"⚠ {w}" for w in bundle.warnings))

    def show_error(self, message: str) -> None:
        self._set_text(self.header_text, "")
        self._set_text(self.source_text, "")
        self.stats_var.set("오류")
        self.warn_var.set(f"✖ {message}")

    def _set_text(self, widget: tk.Text, content: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", content)
        widget.configure(state="disabled")
