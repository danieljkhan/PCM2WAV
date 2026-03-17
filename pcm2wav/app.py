"""PCM to WAV Converter 메인 GUI 앱.

Tkinter 기반 GUI 앱. 스레드 안전 아키텍처 (queue.Queue + root.after 폴링).
"""

from __future__ import annotations

import contextlib
import logging
import queue
import threading
import tkinter as tk
from enum import Enum, auto
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING, Any

import pcm2wav
from pcm2wav.converter import batch_convert
from pcm2wav.widgets import FileListPanel, ParameterPanel

if TYPE_CHECKING:
    from pcm2wav.models import ConversionResult, PcmFormat

logger = logging.getLogger(__name__)

POLL_INTERVAL_MS: int = 100
RESET_DELAY_MS: int = 2000

# Extensions that get replaced with .wav
_REPLACEABLE_EXTENSIONS: frozenset[str] = frozenset(
    {".pcm", ".raw", ".bin", ".dat", ".snd"},
)


class _AppState(Enum):
    """GUI 상태 머신 상태."""

    IDLE = auto()
    CONVERTING = auto()
    COMPLETED = auto()
    CANCELLED = auto()
    ERROR = auto()


class _DuplicateMode(Enum):
    """출력 파일 중복 처리 모드."""

    OVERWRITE = "overwrite"
    SKIP = "skip"
    NUMBER = "number"


def _build_output_path(
    input_path: Path,
    output_dir: Path | None,
    duplicate_mode: _DuplicateMode,
) -> Path | None:
    """입력 파일 경로로부터 출력 WAV 파일 경로를 생성.

    Args:
        input_path: 입력 PCM 파일 경로.
        output_dir: 출력 디렉토리. None이면 입력 파일과 같은 폴더.
        duplicate_mode: 중복 처리 모드.

    Returns:
        출력 WAV 경로. 건너뛰기 모드에서 파일이 이미 존재하면 None.
    """
    # Determine output directory
    target_dir = output_dir if output_dir is not None else input_path.parent

    # Build base output filename
    suffix_lower = input_path.suffix.lower()
    if suffix_lower in _REPLACEABLE_EXTENSIONS:
        stem = input_path.stem
    elif input_path.suffix == "":
        stem = input_path.name
    else:
        stem = input_path.stem

    base_path = target_dir / f"{stem}.wav"

    if not base_path.exists():
        return base_path

    # Handle duplicates
    if duplicate_mode == _DuplicateMode.OVERWRITE:
        return base_path
    if duplicate_mode == _DuplicateMode.SKIP:
        return None
    # NUMBER mode
    counter = 1
    while True:
        numbered_path = target_dir / f"{stem}_{counter}.wav"
        if not numbered_path.exists():
            return numbered_path
        counter += 1


def _is_directory_writable(directory: Path) -> bool:
    """디렉터리에 파일을 쓸 수 있는지 확인.

    임시 파일을 생성/삭제하여 실제 쓰기 가능 여부를 검증한다.

    Args:
        directory: 검사할 디렉터리 경로.

    Returns:
        쓰기 가능하면 True.
    """
    test_path = directory / ".pcm2wav_write_test.tmp"
    try:
        test_path.write_bytes(b"t")
    except OSError:
        return False
    with contextlib.suppress(OSError):
        test_path.unlink()
    return True


class Pcm2WavApp:
    """PCM to WAV Converter 메인 앱.

    Tkinter GUI와 배치 변환 엔진을 통합한다.
    """

    def __init__(self) -> None:
        """앱 초기화: 윈도우, 위젯, 이벤트, 큐 설정."""
        self.root = tk.Tk()
        self.root.title(f"PCM to WAV Converter v{pcm2wav.__version__}")
        self.root.geometry("750x600")
        self.root.minsize(650, 500)

        self._apply_theme()

        # Thread-safe communication
        self.msg_queue: queue.Queue[tuple[Any, ...]] = queue.Queue()
        self._cancel_event = threading.Event()
        self._convert_thread_ref: threading.Thread | None = None

        # App state
        self._state = _AppState.IDLE

        self._build_ui()
        self._bind_shortcuts()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(POLL_INTERVAL_MS, self._poll_queue)

    def _apply_theme(self) -> None:
        """테마 적용 (vista -> winnative -> clam fallback)."""
        style = ttk.Style()
        available = style.theme_names()
        for theme in ("vista", "winnative", "clam"):
            if theme in available:
                style.theme_use(theme)
                logger.debug("테마 적용: %s", theme)
                break

    def _build_ui(self) -> None:
        """메인 UI 레이아웃을 구성."""
        self.root.columnconfigure(0, weight=1)
        # Row weights: format=0, files=1(expand), output=0, status=0, buttons=0
        self.root.rowconfigure(0, weight=0)
        self.root.rowconfigure(1, weight=1)
        self.root.rowconfigure(2, weight=0)
        self.root.rowconfigure(3, weight=0)
        self.root.rowconfigure(4, weight=0)
        self.root.rowconfigure(5, weight=0)

        # Row 0: Parameter Panel
        self._param_panel = ParameterPanel(self.root)
        self._param_panel.grid(
            row=0,
            column=0,
            sticky=tk.EW,
            padx=10,
            pady=(5, 0),
        )

        # Row 1: File List Panel
        self._file_panel = FileListPanel(self.root)
        self._file_panel.grid(
            row=1,
            column=0,
            sticky=tk.NSEW,
            padx=10,
            pady=(5, 0),
        )

        # Row 2: Output Settings
        self._build_output_settings()

        # Row 3: Status + Progress
        self._build_status_area()

        # Row 4: Action Buttons
        self._build_action_buttons()

    def _build_output_settings(self) -> None:
        """출력 설정 프레임 구성."""
        frame = ttk.LabelFrame(
            self.root,
            text="출력 설정",
            padding=(10, 5),
        )
        frame.grid(row=2, column=0, sticky=tk.EW, padx=10, pady=(5, 0))
        frame.columnconfigure(1, weight=1)

        # Row 0: Output folder
        ttk.Label(frame, text="출력 폴더:").grid(
            row=0,
            column=0,
            sticky=tk.W,
            padx=(0, 5),
            pady=2,
        )
        self._output_dir_var = tk.StringVar()
        self._output_dir_entry = ttk.Entry(
            frame,
            textvariable=self._output_dir_var,
        )
        self._output_dir_entry.grid(
            row=0,
            column=1,
            sticky=tk.EW,
            padx=(0, 5),
            pady=2,
        )
        self._browse_btn = ttk.Button(
            frame,
            text="찾아보기..",
            command=self._on_browse_output,
        )
        self._browse_btn.grid(row=0, column=2, pady=2)

        # Row 1: Same folder checkbox
        self._same_folder_var = tk.BooleanVar(value=True)
        self._same_folder_check = ttk.Checkbutton(
            frame,
            text="입력 파일과 같은 폴더에 저장",
            variable=self._same_folder_var,
            command=self._on_same_folder_toggle,
        )
        self._same_folder_check.grid(
            row=1,
            column=0,
            columnspan=3,
            sticky=tk.W,
            pady=2,
        )

        # Row 2: Duplicate handling
        dup_frame = ttk.Frame(frame)
        dup_frame.grid(
            row=2,
            column=0,
            columnspan=3,
            sticky=tk.W,
            pady=2,
        )
        ttk.Label(dup_frame, text="중복 시:").pack(side=tk.LEFT, padx=(0, 5))

        self._duplicate_var = tk.StringVar(
            value=_DuplicateMode.OVERWRITE.value,
        )
        ttk.Radiobutton(
            dup_frame,
            text="덮어쓰기",
            variable=self._duplicate_var,
            value=_DuplicateMode.OVERWRITE.value,
        ).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(
            dup_frame,
            text="건너뛰기",
            variable=self._duplicate_var,
            value=_DuplicateMode.SKIP.value,
        ).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(
            dup_frame,
            text="번호 추가",
            variable=self._duplicate_var,
            value=_DuplicateMode.NUMBER.value,
        ).pack(side=tk.LEFT)

        # Apply initial same-folder state
        self._on_same_folder_toggle()

    def _build_status_area(self) -> None:
        """상태 라벨과 프로그래스바 구성."""
        status_frame = ttk.Frame(self.root)
        status_frame.grid(
            row=3,
            column=0,
            sticky=tk.EW,
            padx=10,
            pady=(5, 0),
        )
        status_frame.columnconfigure(0, weight=1)

        self._status_var = tk.StringVar(value="준비")
        self._status_label = ttk.Label(
            status_frame,
            textvariable=self._status_var,
        )
        self._status_label.grid(row=0, column=0, sticky=tk.W, pady=(0, 2))

        self._progress_var = tk.DoubleVar(value=0.0)
        self._progressbar = ttk.Progressbar(
            status_frame,
            orient=tk.HORIZONTAL,
            mode="determinate",
            variable=self._progress_var,
            maximum=100,
        )
        self._progressbar.grid(row=1, column=0, sticky=tk.EW)

    def _build_action_buttons(self) -> None:
        """변환/취소 버튼 구성."""
        btn_frame = ttk.Frame(self.root)
        btn_frame.grid(
            row=4,
            column=0,
            sticky=tk.EW,
            padx=10,
            pady=10,
        )
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)

        self._start_btn = ttk.Button(
            btn_frame,
            text="변환 시작",
            command=self._start_conversion,
        )
        self._start_btn.grid(row=0, column=0, sticky=tk.EW, padx=(0, 5))

        self._cancel_btn = ttk.Button(
            btn_frame,
            text="취소",
            command=self._cancel_conversion,
        )
        self._cancel_btn.grid(row=0, column=1, sticky=tk.EW, padx=(5, 0))
        self._cancel_btn.state(["disabled"])  # type: ignore[no-untyped-call]

    def _bind_shortcuts(self) -> None:
        """키보드 단축키 바인딩."""
        self.root.bind("<Control-o>", self._shortcut_add_files)
        self.root.bind("<Control-O>", self._shortcut_add_files)
        self.root.bind("<Control-Shift-O>", self._shortcut_add_folder)
        self.root.bind("<Delete>", self._shortcut_remove_selected)
        self.root.bind("<Return>", self._shortcut_start)
        self.root.bind("<Control-Return>", self._shortcut_start)
        self.root.bind("<Escape>", self._shortcut_cancel)

    def _shortcut_add_files(self, _event: tk.Event[Any]) -> None:
        """Ctrl+O: 파일 추가."""
        if self._state == _AppState.IDLE:
            self._file_panel._on_add_files()

    def _shortcut_add_folder(self, _event: tk.Event[Any]) -> None:
        """Ctrl+Shift+O: 폴더 추가."""
        if self._state == _AppState.IDLE:
            self._file_panel._on_add_folder()

    def _shortcut_remove_selected(self, _event: tk.Event[Any]) -> None:
        """Delete: 선택 파일 제거."""
        if self._state == _AppState.IDLE:
            self._file_panel._on_remove_selected()

    def _shortcut_start(self, _event: tk.Event[Any]) -> None:
        """Enter/Ctrl+Enter: 변환 시작."""
        if self._state == _AppState.IDLE:
            self._start_conversion()

    def _shortcut_cancel(self, _event: tk.Event[Any]) -> None:
        """Escape: 변환 취소."""
        if self._state == _AppState.CONVERTING:
            self._cancel_conversion()

    def _on_browse_output(self) -> None:
        """출력 폴더 찾아보기 다이얼로그."""
        folder = filedialog.askdirectory(title="출력 폴더 선택")
        if folder:
            self._output_dir_var.set(folder)

    def _on_same_folder_toggle(self) -> None:
        """'입력 파일과 같은 폴더에 저장' 체크박스 토글 처리."""
        if self._same_folder_var.get():
            self._output_dir_entry.configure(state="disabled")
            self._browse_btn.state(  # type: ignore[no-untyped-call]
                ["disabled"],
            )
        else:
            self._output_dir_entry.configure(state="normal")
            self._browse_btn.state(  # type: ignore[no-untyped-call]
                ["!disabled"],
            )

    def _set_state(self, new_state: _AppState) -> None:
        """앱 상태를 전환하고 UI를 갱신.

        Args:
            new_state: 새로운 상태.
        """
        self._state = new_state
        logger.debug("상태 전환: %s", new_state.name)

        if new_state == _AppState.IDLE:
            self._param_panel.set_enabled(True)
            self._file_panel.set_enabled(True)
            self._start_btn.state(["!disabled"])  # type: ignore[no-untyped-call]
            self._cancel_btn.state(["disabled"])  # type: ignore[no-untyped-call]
            self._enable_output_settings(True)
        elif new_state == _AppState.CONVERTING:
            self._param_panel.set_enabled(False)
            self._file_panel.set_enabled(False)
            self._start_btn.state(["disabled"])  # type: ignore[no-untyped-call]
            self._cancel_btn.state(["!disabled"])  # type: ignore[no-untyped-call]
            self._enable_output_settings(False)
        elif new_state in (
            _AppState.COMPLETED,
            _AppState.CANCELLED,
            _AppState.ERROR,
        ):
            self._param_panel.set_enabled(True)
            self._file_panel.set_enabled(True)
            self._start_btn.state(["!disabled"])  # type: ignore[no-untyped-call]
            self._cancel_btn.state(["disabled"])  # type: ignore[no-untyped-call]
            self._enable_output_settings(True)

            if new_state != _AppState.ERROR:
                self.root.after(RESET_DELAY_MS, self._reset_to_idle)
            else:
                self._reset_to_idle()

    def _enable_output_settings(self, enabled: bool) -> None:
        """출력 설정 위젯의 활성화/비활성화.

        Args:
            enabled: True면 활성화.
        """
        if enabled:
            self._same_folder_check.configure(state="normal")
            self._on_same_folder_toggle()  # Restore based on checkbox
        else:
            self._output_dir_entry.configure(state="disabled")
            self._browse_btn.state(  # type: ignore[no-untyped-call]
                ["disabled"],
            )
            self._same_folder_check.configure(state="disabled")

    def _reset_to_idle(self) -> None:
        """IDLE 상태로 복귀 + 프로그래스바 리셋."""
        try:
            self._progress_var.set(0.0)
            self._status_var.set("준비")
        except tk.TclError:
            pass  # 윈도우가 이미 파괴된 경우
        self._state = _AppState.IDLE

    def _start_conversion(self) -> None:
        """변환 시작. 입력 검증 후 워커 스레드 생성."""
        if self._file_panel.is_empty():
            messagebox.showwarning("알림", "변환할 파일을 추가해주세요.")
            return

        # Validate format
        try:
            fmt = self._param_panel.get_format()
        except (ValueError, Exception) as exc:
            messagebox.showerror("포맷 오류", str(exc))
            return

        # Build output paths
        files = self._file_panel.get_files()
        same_folder = self._same_folder_var.get()

        output_dir: Path | None = None
        if not same_folder:
            dir_str = self._output_dir_var.get().strip()
            if not dir_str:
                messagebox.showwarning("알림", "출력 폴더를 지정해주세요.")
                return
            output_dir = Path(dir_str)
            if not output_dir.exists():
                try:
                    output_dir.mkdir(parents=True, exist_ok=True)
                except OSError as exc:
                    messagebox.showerror(
                        "폴더 오류",
                        f"출력 폴더를 생성할 수 없습니다: {exc}",
                    )
                    return

        dup_mode = _DuplicateMode(self._duplicate_var.get())

        # Build file pairs
        file_pairs: list[tuple[Path, Path]] = []
        skipped_count = 0
        for input_path in files:
            out_path = _build_output_path(input_path, output_dir, dup_mode)
            if out_path is None:
                # Skip mode: file exists
                self._file_panel.update_status(
                    input_path,
                    "건너뜀 (파일 존재)",
                )
                skipped_count += 1
                continue
            file_pairs.append((input_path, out_path))

        if not file_pairs:
            msg = "변환할 파일이 없습니다."
            if skipped_count > 0:
                msg += f" ({skipped_count}개 파일 건너뜀)"
            messagebox.showinfo("알림", msg)
            return

        # Check output directories are writable
        unwritable_dirs: list[Path] = []
        checked_dirs: set[Path] = set()
        for _, out_path in file_pairs:
            parent = out_path.parent
            if parent not in checked_dirs:
                checked_dirs.add(parent)
                if not _is_directory_writable(parent):
                    unwritable_dirs.append(parent)

        if unwritable_dirs:
            dirs_text = "\n".join(str(d) for d in unwritable_dirs)
            messagebox.showerror(
                "쓰기 오류",
                f"다음 출력 폴더에 파일을 쓸 수 없습니다:\n{dirs_text}\n\n"
                "Windows 보안 설정(제어된 폴더 액세스)이 쓰기를\n"
                "차단하고 있을 수 있습니다.\n"
                "다른 출력 폴더를 선택해주세요.",
            )
            return

        # Reset statuses for files to be converted
        for input_path, _ in file_pairs:
            self._file_panel.update_status(input_path, "대기 중")

        self._set_state(_AppState.CONVERTING)
        self._cancel_event.clear()

        self._convert_thread_ref = threading.Thread(
            target=self._convert_thread,
            args=(file_pairs, fmt),
            daemon=True,
        )
        self._convert_thread_ref.start()
        logger.info(
            "변환 시작: %d개 파일, %s",
            len(file_pairs),
            fmt,
        )

    def _convert_thread(
        self,
        file_pairs: list[tuple[Path, Path]],
        fmt: PcmFormat,
    ) -> None:
        """워커 스레드: 배치 변환 실행 및 결과를 큐로 전송.

        Args:
            file_pairs: (입력, 출력) 경로 쌍 목록.
            fmt: PCM 포맷 파라미터.
        """
        completed = False
        try:

            def progress_cb(
                file_idx: int,
                total: int,
                bytes_done: int,
                bytes_total: int,
            ) -> None:
                self.msg_queue.put(
                    (
                        "file_progress",
                        file_idx,
                        total,
                        bytes_done,
                        bytes_total,
                    ),
                )

            results = batch_convert(
                files=file_pairs,
                fmt=fmt,
                progress_callback=progress_cb,
                cancel_event=self._cancel_event,
            )

            # Post individual file completion results
            for i, result in enumerate(results):
                self.msg_queue.put(("file_complete", i, result))

            self.msg_queue.put(("batch_complete", results))
            completed = True

        except Exception as exc:
            logger.exception("변환 스레드 오류")
            self.msg_queue.put(("error", str(exc)))
            completed = True
        finally:
            if not completed:
                self.msg_queue.put(("error", "변환 스레드가 예기치 않게 종료됨"))

    def _cancel_conversion(self) -> None:
        """변환 취소 요청."""
        if self._state == _AppState.CONVERTING:
            self._cancel_event.set()
            self._status_var.set("취소 중...")
            logger.info("변환 취소 요청")

    def _poll_queue(self) -> None:
        """메인 스레드에서 메시지 큐를 폴링하여 GUI 업데이트."""
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                try:
                    self._handle_message(msg)
                except Exception:
                    logger.exception("메시지 처리 오류: %s", msg)
        except queue.Empty:
            pass
        self.root.after(POLL_INTERVAL_MS, self._poll_queue)

    def _handle_message(self, msg: tuple[Any, ...]) -> None:
        """큐 메시지 처리.

        Args:
            msg: (message_type, *args) 형태의 메시지 튜플.
        """
        msg_type: str = msg[0]

        if msg_type == "file_progress":
            file_idx_int: int = msg[1]
            total_files_int: int = msg[2]
            bytes_done_int: int = msg[3]
            bytes_total_int: int = msg[4]

            # Update status label
            files = self._file_panel.get_files()
            if file_idx_int < len(files):
                filename = files[file_idx_int].name
                self._status_var.set(
                    f"변환 중: {filename} ({file_idx_int + 1}/{total_files_int} 파일)"
                )

            # Update progress bar
            if bytes_total_int > 0:
                percent = (bytes_done_int / bytes_total_int) * 100
                self._progress_var.set(min(percent, 100.0))

        elif msg_type == "file_complete":
            result_obj: ConversionResult = msg[2]

            if result_obj.success:
                status = "변환완료"
            else:
                error_short = result_obj.error_message or "알 수 없는 오류"
                if len(error_short) > 30:
                    error_short = error_short[:27] + "..."
                status = f"오류: {error_short}"

            self._file_panel.update_status(result_obj.input_path, status)

        elif msg_type == "batch_complete":
            results: list[ConversionResult] = msg[1]

            success_count = sum(1 for r in results if r.success)
            fail_count = sum(1 for r in results if not r.success)
            total_count = len(results)

            was_cancelled = self._cancel_event.is_set()

            if was_cancelled:
                self._status_var.set(f"취소됨: {success_count}/{total_count}개 변환 완료")
                self._set_state(_AppState.CANCELLED)
            elif fail_count == total_count and total_count > 0:
                self._status_var.set("변환 실패: 모든 파일에서 오류 발생")
                self._set_state(_AppState.ERROR)
            else:
                elapsed = sum(r.elapsed_seconds for r in results)
                self._status_var.set(
                    f"완료: {success_count}개 성공, {fail_count}개 실패 ({elapsed:.1f}초)"
                )
                self._progress_var.set(100.0)
                self._set_state(_AppState.COMPLETED)

            logger.info(
                "배치 변환 완료: %d 성공, %d 실패, 취소=%s",
                success_count,
                fail_count,
                was_cancelled,
            )

        elif msg_type == "error":
            error_msg: str = msg[1]
            self._status_var.set(f"오류: {error_msg}")
            messagebox.showerror("변환 오류", error_msg)
            self._set_state(_AppState.ERROR)

    def _generate_output_path(
        self,
        input_path: Path,
        output_dir: Path,
    ) -> Path:
        """입력 파일 경로로부터 출력 WAV 경로를 생성.

        항상 번호 추가 모드를 사용하여 유일한 경로를 보장한다.

        Args:
            input_path: 입력 PCM 파일 경로.
            output_dir: 출력 디렉토리.

        Returns:
            출력 WAV 경로 (항상 유일한 경로).
        """
        result = _build_output_path(
            input_path,
            output_dir,
            _DuplicateMode.NUMBER,
        )
        # NUMBER mode always returns a non-None path
        assert result is not None  # noqa: S101
        return result

    def _on_close(self) -> None:
        """윈도우 닫기 핸들러. 변환 중이면 확인 다이얼로그 표시."""
        if self._convert_thread_ref is not None and self._convert_thread_ref.is_alive():
            if not messagebox.askokcancel(
                "종료 확인",
                "변환이 진행 중입니다. 종료하시겠습니까?",
            ):
                return
            self._cancel_event.set()
            self._convert_thread_ref.join(timeout=5.0)
        self.root.destroy()

    def run(self) -> None:
        """앱 메인 루프 시작."""
        self.root.mainloop()
