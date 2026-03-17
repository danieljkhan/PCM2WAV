"""PCM2WAV 커스텀 GUI 위젯.

ParameterPanel: PCM 포맷 파라미터 설정 패널.
FileListPanel: 파일 목록 관리 패널.
"""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING, Any

from pcm2wav.models import ByteOrder, PcmFormat
from pcm2wav.presets import DEFAULT_PRESET_NAME, PRESETS

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

# ParameterPanel constants
SAMPLE_RATE_VALUES: list[str] = [
    "8000",
    "11025",
    "16000",
    "22050",
    "44100",
    "48000",
    "96000",
]
BIT_DEPTH_VALUES: list[str] = ["8", "16", "24"]
CHANNEL_DISPLAY: dict[str, int] = {"Mono": 1, "Stereo": 2}
CHANNEL_VALUES: list[str] = list(CHANNEL_DISPLAY.keys())
BYTE_ORDER_DISPLAY: dict[str, ByteOrder] = {
    "Little-Endian": ByteOrder.LITTLE_ENDIAN,
    "Big-Endian": ByteOrder.BIG_ENDIAN,
}
BYTE_ORDER_VALUES: list[str] = list(BYTE_ORDER_DISPLAY.keys())
SIGNED_DISPLAY: dict[str, bool] = {"Signed": True, "Unsigned": False}
SIGNED_VALUES: list[str] = list(SIGNED_DISPLAY.keys())

# FileListPanel constants
PCM_EXTENSIONS: frozenset[str] = frozenset({".pcm", ".raw", ".bin", ".dat", ".snd"})
FILE_FILTER: list[tuple[str, str]] = [
    ("PCM 파일", "*.pcm;*.raw;*.bin;*.dat;*.snd"),
    ("모든 파일", "*.*"),
]


def _format_file_size(size_bytes: int) -> str:
    """파일 크기를 사람이 읽기 쉬운 형식으로 변환.

    Args:
        size_bytes: 바이트 단위 파일 크기.

    Returns:
        포맷된 크기 문자열.
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


class ParameterPanel(ttk.LabelFrame):
    """PCM 포맷 파라미터 설정 패널.

    프리셋 선택 또는 커스텀 입력으로 PcmFormat을 구성한다.
    """

    def __init__(self, parent: tk.Misc) -> None:
        """ParameterPanel 초기화.

        Args:
            parent: 부모 위젯.
        """
        super().__init__(parent, text="포맷 설정", padding=(10, 5))
        self._preset_names: list[str] = list(PRESETS.keys())
        self._build_ui()
        self._bind_events()
        self._select_preset(DEFAULT_PRESET_NAME)

    def _build_ui(self) -> None:
        """UI 위젯을 생성하고 grid 레이아웃으로 배치."""
        self.columnconfigure(1, weight=1)
        self.columnconfigure(3, weight=1)

        # Row 0: Preset (full width)
        ttk.Label(self, text="프리셋:").grid(
            row=0,
            column=0,
            sticky=tk.W,
            padx=(0, 5),
            pady=2,
        )
        self._preset_var = tk.StringVar()
        self._preset_combo = ttk.Combobox(
            self,
            textvariable=self._preset_var,
            values=self._preset_names,
            state="readonly",
        )
        self._preset_combo.grid(
            row=0,
            column=1,
            columnspan=3,
            sticky=tk.EW,
            pady=2,
        )

        # Row 1: Sample rate + Bit depth
        ttk.Label(self, text="샘플레이트:").grid(
            row=1,
            column=0,
            sticky=tk.W,
            padx=(0, 5),
            pady=2,
        )
        self._sample_rate_var = tk.StringVar()
        self._sample_rate_combo = ttk.Combobox(
            self,
            textvariable=self._sample_rate_var,
            values=SAMPLE_RATE_VALUES,
        )
        self._sample_rate_combo.grid(
            row=1,
            column=1,
            sticky=tk.EW,
            padx=(0, 15),
            pady=2,
        )

        ttk.Label(self, text="비트깊이:").grid(
            row=1,
            column=2,
            sticky=tk.W,
            padx=(0, 5),
            pady=2,
        )
        self._bit_depth_var = tk.StringVar()
        self._bit_depth_combo = ttk.Combobox(
            self,
            textvariable=self._bit_depth_var,
            values=BIT_DEPTH_VALUES,
            state="readonly",
        )
        self._bit_depth_combo.grid(
            row=1,
            column=3,
            sticky=tk.EW,
            pady=2,
        )

        # Row 2: Channels + Byte order
        ttk.Label(self, text="채널:").grid(
            row=2,
            column=0,
            sticky=tk.W,
            padx=(0, 5),
            pady=2,
        )
        self._channels_var = tk.StringVar()
        self._channels_combo = ttk.Combobox(
            self,
            textvariable=self._channels_var,
            values=CHANNEL_VALUES,
            state="readonly",
        )
        self._channels_combo.grid(
            row=2,
            column=1,
            sticky=tk.EW,
            padx=(0, 15),
            pady=2,
        )

        ttk.Label(self, text="바이트 오더:").grid(
            row=2,
            column=2,
            sticky=tk.W,
            padx=(0, 5),
            pady=2,
        )
        self._byte_order_var = tk.StringVar()
        self._byte_order_combo = ttk.Combobox(
            self,
            textvariable=self._byte_order_var,
            values=BYTE_ORDER_VALUES,
            state="readonly",
        )
        self._byte_order_combo.grid(
            row=2,
            column=3,
            sticky=tk.EW,
            pady=2,
        )

        # Row 3: Signed
        ttk.Label(self, text="부호:").grid(
            row=3,
            column=0,
            sticky=tk.W,
            padx=(0, 5),
            pady=2,
        )
        self._signed_var = tk.StringVar()
        self._signed_combo = ttk.Combobox(
            self,
            textvariable=self._signed_var,
            values=SIGNED_VALUES,
            state="readonly",
        )
        self._signed_combo.grid(
            row=3,
            column=1,
            sticky=tk.EW,
            padx=(0, 15),
            pady=2,
        )

        # Store parameter combos for bulk enable/disable
        self._param_combos: list[ttk.Combobox] = [
            self._sample_rate_combo,
            self._bit_depth_combo,
            self._channels_combo,
            self._byte_order_combo,
            self._signed_combo,
        ]

    def _bind_events(self) -> None:
        """이벤트 바인딩 설정."""
        self._preset_combo.bind("<<ComboboxSelected>>", self._on_preset_change)
        self._bit_depth_combo.bind(
            "<<ComboboxSelected>>",
            self._on_bit_depth_change,
        )
        self._sample_rate_combo.bind("<FocusOut>", self._on_sample_rate_validate)

    def _on_preset_change(self, _event: tk.Event[Any]) -> None:
        """프리셋 변경 시 호출."""
        name = self._preset_var.get()
        self._select_preset(name)

    def _select_preset(self, name: str) -> None:
        """프리셋을 선택하고 UI를 갱신.

        Args:
            name: 프리셋 이름.
        """
        self._preset_var.set(name)
        fmt = PRESETS.get(name)

        if fmt is not None:
            # Preset selected: fill fields and disable
            self.set_format(fmt)
            self._set_params_state("disabled")
        else:
            # Custom: enable all fields
            self._set_params_state("normal")
            self._apply_bit_depth_rule()

    def _set_params_state(self, state: str) -> None:
        """파라미터 콤보박스의 상태를 일괄 설정.

        Args:
            state: "normal", "readonly", "disabled" 중 하나.
        """
        for combo in self._param_combos:
            if combo is self._sample_rate_combo:
                combo.configure(state=state)
            elif state == "normal":
                combo.configure(state="readonly")
            else:
                combo.configure(state=state)

        # After setting state, apply bit depth rule for signed field
        if state != "disabled":
            self._apply_bit_depth_rule()

    def _on_bit_depth_change(self, _event: tk.Event[Any]) -> None:
        """비트깊이 변경 시 부호 필드 상태 제어."""
        self._apply_bit_depth_rule()

    def _apply_bit_depth_rule(self) -> None:
        """비트깊이에 따라 부호 필드를 제어.

        8-bit: 부호 필드 활성화.
        16/24-bit: 부호 필드 비활성화 + Signed 고정.
        """
        try:
            bit_depth = int(self._bit_depth_var.get())
        except ValueError:
            return

        if bit_depth == 8:
            self._signed_combo.configure(state="readonly")
        else:
            self._signed_var.set("Signed")
            self._signed_combo.configure(state="disabled")

    def _on_sample_rate_validate(self, _event: tk.Event[Any]) -> None:
        """샘플레이트 입력값 유효성 검증 (focus-out 시)."""
        raw = self._sample_rate_var.get().strip()
        if not raw:
            self._sample_rate_var.set("44100")
            return
        try:
            value = int(raw)
            if value < 1 or value > 384_000:
                raise ValueError
        except ValueError:
            logger.warning("잘못된 샘플레이트 입력: %s", raw)
            self._sample_rate_var.set("44100")

    def get_format(self) -> PcmFormat:
        """현재 UI 값으로 PcmFormat 생성.

        Returns:
            구성된 PcmFormat 인스턴스.

        Raises:
            ValueError: 유효하지 않은 파라미터 값.
        """
        try:
            sample_rate = int(self._sample_rate_var.get().strip())
        except ValueError as exc:
            raise ValueError(f"잘못된 샘플레이트: {self._sample_rate_var.get()}") from exc

        try:
            bit_depth = int(self._bit_depth_var.get())
        except ValueError as exc:
            raise ValueError(f"잘못된 비트깊이: {self._bit_depth_var.get()}") from exc

        channels_str = self._channels_var.get()
        if channels_str not in CHANNEL_DISPLAY:
            raise ValueError(f"잘못된 채널: {channels_str}")
        channels = CHANNEL_DISPLAY[channels_str]

        byte_order_str = self._byte_order_var.get()
        if byte_order_str not in BYTE_ORDER_DISPLAY:
            raise ValueError(f"잘못된 바이트 오더: {byte_order_str}")
        byte_order = BYTE_ORDER_DISPLAY[byte_order_str]

        signed_str = self._signed_var.get()
        if signed_str not in SIGNED_DISPLAY:
            raise ValueError(f"잘못된 부호 설정: {signed_str}")
        signed = SIGNED_DISPLAY[signed_str]

        return PcmFormat(
            sample_rate=sample_rate,
            bit_depth=bit_depth,
            channels=channels,
            byte_order=byte_order,
            signed=signed,
        )

    def set_format(self, fmt: PcmFormat) -> None:
        """주어진 PcmFormat으로 UI 필드 갱신.

        Args:
            fmt: 설정할 PcmFormat.
        """
        self._sample_rate_var.set(str(fmt.sample_rate))
        self._bit_depth_var.set(str(fmt.bit_depth))

        # Channels: reverse lookup
        for display_name, ch_value in CHANNEL_DISPLAY.items():
            if ch_value == fmt.channels:
                self._channels_var.set(display_name)
                break

        # Byte order: reverse lookup
        for display_name, bo_value in BYTE_ORDER_DISPLAY.items():
            if bo_value == fmt.byte_order:
                self._byte_order_var.set(display_name)
                break

        # Signed: reverse lookup
        for display_name, s_value in SIGNED_DISPLAY.items():
            if s_value == fmt.signed:
                self._signed_var.set(display_name)
                break

    def set_enabled(self, enabled: bool) -> None:
        """전체 패널 활성화/비활성화 (변환 중 사용).

        Args:
            enabled: True면 활성화, False면 비활성화.
        """
        if enabled:
            self._preset_combo.configure(state="readonly")
            # Restore state based on preset selection
            name = self._preset_var.get()
            fmt = PRESETS.get(name)
            if fmt is not None:
                self._set_params_state("disabled")
            else:
                self._set_params_state("normal")
        else:
            self._preset_combo.configure(state="disabled")
            self._set_params_state("disabled")


class FileListPanel(ttk.LabelFrame):
    """파일 목록 관리 패널.

    Treeview로 파일 목록을 표시하고, 추가/제거 기능을 제공한다.
    """

    def __init__(self, parent: tk.Misc) -> None:
        """FileListPanel 초기화.

        Args:
            parent: 부모 위젯.
        """
        super().__init__(parent, text="입력 파일", padding=(10, 5))
        self._file_paths: dict[str, Path] = {}  # iid -> Path
        self._path_to_iid: dict[str, str] = {}  # str(path) -> iid
        self._build_ui()

    def _build_ui(self) -> None:
        """UI 위젯을 생성하고 배치."""
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # Button frame
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=0, column=0, sticky=tk.EW, pady=(0, 5))

        self._btn_add_files = ttk.Button(
            btn_frame,
            text="파일 추가",
            command=self._on_add_files,
        )
        self._btn_add_files.pack(side=tk.LEFT, padx=(0, 5))

        self._btn_add_folder = ttk.Button(
            btn_frame,
            text="폴더 추가",
            command=self._on_add_folder,
        )
        self._btn_add_folder.pack(side=tk.LEFT, padx=(0, 5))

        self._btn_remove_selected = ttk.Button(
            btn_frame,
            text="선택 제거",
            command=self._on_remove_selected,
        )
        self._btn_remove_selected.pack(side=tk.LEFT, padx=(0, 5))

        self._btn_clear_all = ttk.Button(
            btn_frame,
            text="전체 삭제",
            command=self._on_clear_all,
        )
        self._btn_clear_all.pack(side=tk.LEFT)

        self._buttons: list[ttk.Button] = [
            self._btn_add_files,
            self._btn_add_folder,
            self._btn_remove_selected,
            self._btn_clear_all,
        ]

        # Treeview with scrollbar
        tree_frame = ttk.Frame(self)
        tree_frame.grid(row=1, column=0, sticky=tk.NSEW)
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        self._tree = ttk.Treeview(
            tree_frame,
            columns=("filename", "size", "status"),
            show="headings",
            selectmode="extended",
        )
        self._tree.heading("filename", text="파일명", anchor=tk.W)
        self._tree.heading("size", text="크기", anchor=tk.W)
        self._tree.heading("status", text="상태", anchor=tk.W)

        self._tree.column("filename", minwidth=200, stretch=True)
        self._tree.column("size", width=100, minwidth=80, stretch=False)
        self._tree.column("status", width=150, minwidth=100, stretch=False)

        scrollbar = ttk.Scrollbar(
            tree_frame,
            orient=tk.VERTICAL,
            command=self._tree.yview,
        )
        self._tree.configure(yscrollcommand=scrollbar.set)

        self._tree.grid(row=0, column=0, sticky=tk.NSEW)
        scrollbar.grid(row=0, column=1, sticky=tk.NS)

    def _on_add_files(self) -> None:
        """파일 추가 다이얼로그를 열고 선택된 파일을 추가."""
        from pathlib import Path

        paths = filedialog.askopenfilenames(
            title="PCM 파일 선택",
            filetypes=FILE_FILTER,
        )
        if paths:
            file_paths = [Path(p) for p in paths]
            added = self.add_files(file_paths)
            logger.debug("%d개 파일 추가됨", added)

    def _on_add_folder(self) -> None:
        """폴더 추가 다이얼로그를 열고 폴더 내 PCM 파일을 추가."""
        from pathlib import Path

        folder = filedialog.askdirectory(title="PCM 파일 폴더 선택")
        if not folder:
            return

        folder_path = Path(folder)
        file_paths: list[Path] = []
        for item in folder_path.iterdir():
            if item.is_file() and item.suffix.lower() in PCM_EXTENSIONS:
                file_paths.append(item)

        if not file_paths:
            messagebox.showinfo(
                "알림",
                "선택한 폴더에 PCM 파일이 없습니다.\n"
                f"지원 확장자: {', '.join(sorted(PCM_EXTENSIONS))}",
            )
            return

        file_paths.sort(key=lambda p: p.name.lower())
        added = self.add_files(file_paths)
        logger.debug("폴더에서 %d개 파일 추가됨", added)

    def _on_remove_selected(self) -> None:
        """선택된 파일을 목록에서 제거."""
        selected = self._tree.selection()
        for iid in selected:
            if iid in self._file_paths:
                path = self._file_paths[iid]
                path_key = str(path.resolve())
                self._path_to_iid.pop(path_key, None)
                del self._file_paths[iid]
            self._tree.delete(iid)

    def _on_clear_all(self) -> None:
        """전체 파일 목록 삭제."""
        self.clear()

    def add_files(self, paths: list[Path]) -> int:
        """파일 추가. 중복 제외. 추가된 파일 수 반환.

        Args:
            paths: 추가할 파일 경로 목록.

        Returns:
            새로 추가된 파일 수.
        """
        added = 0
        for path in paths:
            path_key = str(path.resolve())
            if path_key in self._path_to_iid:
                continue  # Skip duplicate

            if not path.exists():
                logger.warning("존재하지 않는 파일: %s", path)
                continue

            size = path.stat().st_size
            size_str = _format_file_size(size)

            iid = self._tree.insert(
                "",
                tk.END,
                values=(path.name, size_str, "준비"),
            )
            self._file_paths[iid] = path
            self._path_to_iid[path_key] = iid
            added += 1

        return added

    def get_files(self) -> list[Path]:
        """현재 파일 목록 반환.

        Returns:
            파일 경로 목록 (Treeview 표시 순서).
        """
        result: list[Path] = []
        for iid in self._tree.get_children():
            if iid in self._file_paths:
                result.append(self._file_paths[iid])
        return result

    def update_status(self, path: Path, status: str) -> None:
        """특정 파일의 상태 컬럼 갱신.

        Args:
            path: 대상 파일 경로.
            status: 새 상태 문자열.
        """
        path_key = str(path.resolve())
        iid = self._path_to_iid.get(path_key)
        if iid is None:
            return
        try:
            if not self._tree.exists(iid):
                return
            current_values = self._tree.item(iid, "values")
            self._tree.item(
                iid,
                values=(current_values[0], current_values[1], status),
            )
        except tk.TclError:
            logger.debug("Treeview 항목 갱신 실패 (삭제됨): %s", path.name)

    def clear(self) -> None:
        """전체 파일 목록 삭제."""
        for iid in self._tree.get_children():
            self._tree.delete(iid)
        self._file_paths.clear()
        self._path_to_iid.clear()

    def is_empty(self) -> bool:
        """파일 목록이 비어있는지 확인.

        Returns:
            비어있으면 True.
        """
        return len(self._file_paths) == 0

    def set_enabled(self, enabled: bool) -> None:
        """버튼 활성화/비활성화 (변환 중 사용).

        Args:
            enabled: True면 활성화, False면 비활성화.
        """
        state_spec = "!disabled" if enabled else "disabled"
        for btn in self._buttons:
            btn.state([state_spec])  # type: ignore[no-untyped-call]
