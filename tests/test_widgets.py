"""Tests for pcm2wav.widgets — ParameterPanel and FileListPanel."""

from __future__ import annotations

import contextlib
import tkinter as tk
from typing import TYPE_CHECKING

import pytest

from pcm2wav.models import ByteOrder, PcmFormat
from pcm2wav.presets import DEFAULT_PRESET_NAME, PRESETS
from pcm2wav.widgets import FileListPanel, ParameterPanel

if TYPE_CHECKING:
    from pathlib import Path


def _tk_available() -> bool:
    """Check if Tk/Tcl is fully functional on this system."""
    try:
        r = tk.Tk()
        r.withdraw()
        r.destroy()
    except tk.TclError:
        return False
    return True


pytestmark = pytest.mark.skipif(not _tk_available(), reason="Tk/Tcl not fully functional")


@pytest.fixture()
def root() -> tk.Tk:
    """Create and destroy a Tk root window for testing."""
    try:
        _root = tk.Tk()
        _root.withdraw()
    except tk.TclError:
        pytest.skip("Tk/Tcl initialization failed")
    yield _root  # type: ignore[misc]
    with contextlib.suppress(tk.TclError):
        _root.destroy()


def _make_file(tmp_path: Path, name: str, size: int) -> Path:
    """Create a temporary file with the given name and size."""
    p = tmp_path / name
    p.write_bytes(b"\x00" * size)
    return p


# ---------------------------------------------------------------------------
# ParameterPanel
# ---------------------------------------------------------------------------


class TestParameterPanel:
    """Validates ParameterPanel widget creation, preset logic, and format I/O."""

    def test_creation(self, root: tk.Tk) -> None:
        """Panel creates without error."""
        panel = ParameterPanel(root)
        assert panel is not None
        root.update_idletasks()

    def test_default_preset_selected(self, root: tk.Tk) -> None:
        """Default preset is selected on init."""
        panel = ParameterPanel(root)
        root.update_idletasks()
        fmt = panel.get_format()
        default_fmt = PRESETS[DEFAULT_PRESET_NAME]
        assert default_fmt is not None
        assert fmt.sample_rate == default_fmt.sample_rate
        assert fmt.bit_depth == default_fmt.bit_depth
        assert fmt.channels == default_fmt.channels

    def test_get_format_default(self, root: tk.Tk) -> None:
        """get_format() returns a valid PcmFormat for the default preset."""
        panel = ParameterPanel(root)
        root.update_idletasks()
        fmt = panel.get_format()
        assert isinstance(fmt, PcmFormat)

    def test_set_format(self, root: tk.Tk) -> None:
        """set_format() updates UI fields correctly."""
        panel = ParameterPanel(root)
        root.update_idletasks()

        target = PcmFormat(
            sample_rate=48000,
            bit_depth=24,
            channels=2,
            byte_order=ByteOrder.BIG_ENDIAN,
            signed=True,
        )
        panel.set_format(target)
        root.update_idletasks()

        result = panel.get_format()
        assert result.sample_rate == 48000
        assert result.bit_depth == 24
        assert result.channels == 2
        assert result.byte_order is ByteOrder.BIG_ENDIAN

    def test_custom_preset_enables_fields(self, root: tk.Tk) -> None:
        """Selecting 'Custom' enables parameter fields for manual input."""
        panel = ParameterPanel(root)
        root.update_idletasks()

        # Set a custom format to trigger Custom mode
        custom_fmt = PcmFormat(
            sample_rate=96000,
            bit_depth=24,
            channels=2,
            byte_order=ByteOrder.BIG_ENDIAN,
        )
        panel.set_format(custom_fmt)
        root.update_idletasks()

        # After setting a non-preset format, get_format should return it
        result = panel.get_format()
        assert result.sample_rate == 96000

    def test_named_preset_disables_fields(self, root: tk.Tk) -> None:
        """Selecting a named preset produces the correct format values."""
        panel = ParameterPanel(root)
        root.update_idletasks()

        # Set a known preset format
        cd_fmt = PRESETS["CD Quality (44100Hz, 16-bit, Stereo)"]
        assert cd_fmt is not None
        panel.set_format(cd_fmt)
        root.update_idletasks()

        result = panel.get_format()
        assert result.sample_rate == 44100
        assert result.bit_depth == 16
        assert result.channels == 2

    def test_8bit_enables_signed_field(self, root: tk.Tk) -> None:
        """When bit_depth is 8, the signed field should allow unsigned."""
        panel = ParameterPanel(root)
        root.update_idletasks()

        fmt_8bit_unsigned = PcmFormat(
            sample_rate=8000,
            bit_depth=8,
            channels=1,
            signed=False,
        )
        panel.set_format(fmt_8bit_unsigned)
        root.update_idletasks()

        result = panel.get_format()
        assert result.bit_depth == 8
        assert result.signed is False

    def test_16bit_disables_signed_field(self, root: tk.Tk) -> None:
        """When bit_depth is 16, signed must be forced to True."""
        panel = ParameterPanel(root)
        root.update_idletasks()

        fmt_16bit = PcmFormat(
            sample_rate=44100,
            bit_depth=16,
            channels=1,
            signed=True,
        )
        panel.set_format(fmt_16bit)
        root.update_idletasks()

        result = panel.get_format()
        assert result.bit_depth == 16
        assert result.signed is True

    def test_get_format_custom_values(self, root: tk.Tk) -> None:
        """Custom values produce correct PcmFormat."""
        panel = ParameterPanel(root)
        root.update_idletasks()

        target = PcmFormat(
            sample_rate=22050,
            bit_depth=8,
            channels=1,
            byte_order=ByteOrder.LITTLE_ENDIAN,
            signed=True,
        )
        panel.set_format(target)
        root.update_idletasks()

        result = panel.get_format()
        assert result.sample_rate == 22050
        assert result.bit_depth == 8
        assert result.channels == 1
        assert result.byte_order is ByteOrder.LITTLE_ENDIAN
        assert result.signed is True

    def test_set_enabled_false(self, root: tk.Tk) -> None:
        """set_enabled(False) disables controls without error."""
        panel = ParameterPanel(root)
        root.update_idletasks()
        panel.set_enabled(False)
        root.update_idletasks()

    def test_set_enabled_true(self, root: tk.Tk) -> None:
        """set_enabled(True) re-enables controls without error."""
        panel = ParameterPanel(root)
        root.update_idletasks()
        panel.set_enabled(False)
        root.update_idletasks()
        panel.set_enabled(True)
        root.update_idletasks()

        # Should still be able to get format after re-enable
        fmt = panel.get_format()
        assert isinstance(fmt, PcmFormat)


# ---------------------------------------------------------------------------
# FileListPanel
# ---------------------------------------------------------------------------


class TestFileListPanel:
    """Validates FileListPanel widget creation, file management, and status."""

    def test_creation(self, root: tk.Tk) -> None:
        """Panel creates without error."""
        panel = FileListPanel(root)
        assert panel is not None
        root.update_idletasks()

    def test_add_files(self, root: tk.Tk, tmp_path: Path) -> None:
        """add_files() adds files and returns the count of newly added files."""
        panel = FileListPanel(root)
        root.update_idletasks()

        f1 = _make_file(tmp_path, "test1.pcm", 100)
        f2 = _make_file(tmp_path, "test2.pcm", 200)
        count = panel.add_files([f1, f2])

        assert count == 2

    def test_add_duplicate_ignored(self, root: tk.Tk, tmp_path: Path) -> None:
        """Same path added twice results in count 0 the second time."""
        panel = FileListPanel(root)
        root.update_idletasks()

        f1 = _make_file(tmp_path, "dup.pcm", 100)
        first_count = panel.add_files([f1])
        assert first_count == 1

        second_count = panel.add_files([f1])
        assert second_count == 0

    def test_get_files(self, root: tk.Tk, tmp_path: Path) -> None:
        """get_files() returns the paths that were added."""
        panel = FileListPanel(root)
        root.update_idletasks()

        f1 = _make_file(tmp_path, "a.pcm", 50)
        f2 = _make_file(tmp_path, "b.raw", 75)
        panel.add_files([f1, f2])

        files = panel.get_files()
        assert len(files) == 2
        # Paths should match (resolve to handle any case differences)
        resolved = {p.resolve() for p in files}
        assert f1.resolve() in resolved
        assert f2.resolve() in resolved

    def test_clear(self, root: tk.Tk, tmp_path: Path) -> None:
        """clear() removes all files from the list."""
        panel = FileListPanel(root)
        root.update_idletasks()

        f1 = _make_file(tmp_path, "clear_test.pcm", 100)
        panel.add_files([f1])
        assert not panel.is_empty()

        panel.clear()
        assert panel.is_empty()
        assert panel.get_files() == []

    def test_is_empty_initial(self, root: tk.Tk) -> None:
        """is_empty() returns True when no files have been added."""
        panel = FileListPanel(root)
        root.update_idletasks()
        assert panel.is_empty() is True

    def test_is_empty_after_add(self, root: tk.Tk, tmp_path: Path) -> None:
        """is_empty() returns False after adding a file."""
        panel = FileListPanel(root)
        root.update_idletasks()

        f1 = _make_file(tmp_path, "notempty.pcm", 50)
        panel.add_files([f1])
        assert panel.is_empty() is False

    def test_update_status(self, root: tk.Tk, tmp_path: Path) -> None:
        """update_status() changes the status column without error."""
        panel = FileListPanel(root)
        root.update_idletasks()

        f1 = _make_file(tmp_path, "status_test.pcm", 100)
        panel.add_files([f1])
        root.update_idletasks()

        # Should not raise
        panel.update_status(f1, "변환완료 ✓")
        root.update_idletasks()

    def test_set_enabled_false(self, root: tk.Tk) -> None:
        """set_enabled(False) disables buttons without error."""
        panel = FileListPanel(root)
        root.update_idletasks()
        panel.set_enabled(False)
        root.update_idletasks()

    def test_set_enabled_true(self, root: tk.Tk) -> None:
        """set_enabled(True) re-enables buttons without error."""
        panel = FileListPanel(root)
        root.update_idletasks()
        panel.set_enabled(False)
        root.update_idletasks()
        panel.set_enabled(True)
        root.update_idletasks()

    def test_file_size_format(self, root: tk.Tk, tmp_path: Path) -> None:
        """Files of various sizes should be added and retrievable."""
        panel = FileListPanel(root)
        root.update_idletasks()

        # Tiny file (bytes range)
        f_small = _make_file(tmp_path, "tiny.pcm", 512)
        # KB range file
        f_kb = _make_file(tmp_path, "medium.pcm", 1536)
        # MB range file (just over 1 MB)
        f_mb = _make_file(tmp_path, "large.pcm", 1_048_576 + 100)

        count = panel.add_files([f_small, f_kb, f_mb])
        assert count == 3

        files = panel.get_files()
        assert len(files) == 3
