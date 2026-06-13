"""메인 윈도우: 설정/미리보기 패널 배선, 디바운스 재생성, 백그라운드 탐색."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from core.config import HashConfig
from core.generators import CodeBundle, generate

from .config_panel import ConfigPanel
from .preview_panel import PreviewPanel

_DEBOUNCE_MS = 300


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Hash Function Generator")
        self.geometry("960x640")  # 최대화 해제 시 돌아갈 기본 크기
        self.minsize(720, 480)
        self._maximize()

        self._debounce_job = None
        self._result_q: "queue.Queue" = queue.Queue()
        self._last_bundle: CodeBundle | None = None
        self._gen_seq = 0  # 오래된 백그라운드 결과 무시용

        self._build()
        self.schedule_regenerate()  # 초기 1회
        self.after(50, self._poll_results)

    def _maximize(self) -> None:
        """시작 시 창을 최대화. 플랫폼별로 안전하게 폴백."""
        try:
            self.state("zoomed")  # Windows / 대부분의 환경
        except tk.TclError:
            try:
                self.attributes("-zoomed", True)  # 일부 Linux(X11)
            except tk.TclError:
                # 최후: 화면 크기에 맞춤
                w, h = self.winfo_screenwidth(), self.winfo_screenheight()
                self.geometry(f"{w}x{h}+0+0")

    def _build(self) -> None:
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)

        self.config_panel = ConfigPanel(paned, on_change=self.schedule_regenerate)
        self.preview_panel = PreviewPanel(paned)
        paned.add(self.config_panel, weight=0)
        paned.add(self.preview_panel, weight=1)

        bar = ttk.Frame(self, padding=6)
        bar.pack(fill="x")
        ttk.Button(bar, text="생성", command=self.schedule_regenerate).pack(side="left")
        ttk.Button(bar, text=".h 저장", command=lambda: self._save("header")).pack(side="left")
        ttk.Button(bar, text=".c 저장", command=lambda: self._save("source")).pack(side="left")
        ttk.Button(bar, text="클립보드 복사(.c)",
                   command=self._copy).pack(side="left")

    # --- 재생성 (디바운스 → 백그라운드 스레드) ---
    def schedule_regenerate(self) -> None:
        if self._debounce_job is not None:
            self.after_cancel(self._debounce_job)
        self._debounce_job = self.after(_DEBOUNCE_MS, self._start_generate)

    def _start_generate(self) -> None:
        self._debounce_job = None
        try:
            cfg = self.config_panel.build_config()
        except Exception as exc:  # noqa: BLE001
            self.preview_panel.show_error(str(exc))
            return
        self._gen_seq += 1
        seq = self._gen_seq
        threading.Thread(target=self._worker, args=(cfg, seq), daemon=True).start()

    def _worker(self, cfg: HashConfig, seq: int) -> None:
        try:
            bundle = generate(cfg)
            self._result_q.put((seq, bundle, None))
        except Exception as exc:  # noqa: BLE001
            self._result_q.put((seq, None, str(exc)))

    def _poll_results(self) -> None:
        try:
            while True:
                seq, bundle, err = self._result_q.get_nowait()
                if seq != self._gen_seq:
                    continue  # 더 최신 요청이 있으므로 폐기
                if err is not None:
                    self.preview_panel.show_error(err)
                    self._last_bundle = None
                else:
                    self.preview_panel.show_bundle(bundle)
                    self._last_bundle = bundle
        except queue.Empty:
            pass
        self.after(50, self._poll_results)

    # --- 저장/복사 ---
    def _save(self, which: str) -> None:
        if not self._last_bundle:
            messagebox.showwarning("저장", "생성된 코드가 없습니다.")
            return
        fn = self.config_panel.func_name.get().strip() or "myhash"
        ext = ".h" if which == "header" else ".c"
        content = getattr(self._last_bundle, which)
        path = filedialog.asksaveasfilename(
            defaultextension=ext, initialfile=fn + ext,
            filetypes=[(f"C {ext}", f"*{ext}"), ("All", "*.*")])
        if path:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)

    def _copy(self) -> None:
        if not self._last_bundle:
            return
        self.clipboard_clear()
        self.clipboard_append(self._last_bundle.source)


def main() -> None:
    App().mainloop()
