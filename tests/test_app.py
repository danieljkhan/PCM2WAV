"""Tests for pcm2wav.app — Pcm2WavApp creation, output paths, and state."""

from __future__ import annotations

import contextlib
import tkinter as tk
from pathlib import Path
from unittest.mock import patch

import pytest

from pcm2wav import __version__
from pcm2wav.app import Pcm2WavApp, _is_directory_writable


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
def app() -> Pcm2WavApp:
    """Create and destroy a Pcm2WavApp instance for testing."""
    try:
        _app = Pcm2WavApp()
        _app.root.withdraw()
    except tk.TclError:
        pytest.skip("Tk/Tcl initialization failed")
    yield _app  # type: ignore[misc]
    with contextlib.suppress(tk.TclError):
        _app.root.destroy()


# ---------------------------------------------------------------------------
# App creation
# ---------------------------------------------------------------------------


class TestAppCreation:
    """Validates that Pcm2WavApp instantiates correctly."""

    def test_app_creates(self, app: Pcm2WavApp) -> None:
        """Pcm2WavApp() instantiates without error."""
        assert app is not None
        assert app.root is not None

    def test_window_title(self, app: Pcm2WavApp) -> None:
        """Window title contains the package version string."""
        title = app.root.title()
        assert __version__ in title

    def test_window_min_size(self, app: Pcm2WavApp) -> None:
        """Window minsize is configured (non-zero dimensions)."""
        app.root.update_idletasks()
        # minsize returns a tuple (width, height) as strings or ints
        min_width = app.root.minsize()[0]
        min_height = app.root.minsize()[1]
        assert int(min_width) > 0
        assert int(min_height) > 0


# ---------------------------------------------------------------------------
# Output path generation
# ---------------------------------------------------------------------------


class TestOutputPathGeneration:
    """Validates output file path derivation logic.

    The app must convert input PCM extensions to .wav and handle
    duplicates with numbered suffixes.
    """

    def test_pcm_to_wav_extension(self, app: Pcm2WavApp, tmp_path: Path) -> None:
        """.pcm extension is replaced with .wav."""
        input_path = tmp_path / "audio.pcm"
        input_path.write_bytes(b"\x00" * 10)
        result = app._generate_output_path(input_path, tmp_path)
        assert result.suffix == ".wav"
        assert result.stem == "audio"

    def test_raw_to_wav_extension(self, app: Pcm2WavApp, tmp_path: Path) -> None:
        """.raw extension is replaced with .wav."""
        input_path = tmp_path / "audio.raw"
        input_path.write_bytes(b"\x00" * 10)
        result = app._generate_output_path(input_path, tmp_path)
        assert result.suffix == ".wav"
        assert result.stem == "audio"

    def test_no_extension_appends_wav(self, app: Pcm2WavApp, tmp_path: Path) -> None:
        """File with no extension gets .wav appended."""
        input_path = tmp_path / "audio"
        input_path.write_bytes(b"\x00" * 10)
        result = app._generate_output_path(input_path, tmp_path)
        assert result.suffix == ".wav"
        assert "audio" in result.stem

    def test_multi_dot_replaces_last(self, app: Pcm2WavApp, tmp_path: Path) -> None:
        """Multi-dot filename replaces only the last extension."""
        input_path = tmp_path / "file.backup.pcm"
        input_path.write_bytes(b"\x00" * 10)
        result = app._generate_output_path(input_path, tmp_path)
        assert result.suffix == ".wav"
        assert result.stem == "file.backup"

    def test_numbered_output(self, app: Pcm2WavApp, tmp_path: Path) -> None:
        """When output file already exists, a numbered suffix is used."""
        input_path = tmp_path / "dup.pcm"
        input_path.write_bytes(b"\x00" * 10)

        # Create the expected output so it already exists
        existing = tmp_path / "dup.wav"
        existing.write_bytes(b"\x00" * 10)

        result = app._generate_output_path(input_path, tmp_path)
        assert result != existing
        assert result.suffix == ".wav"
        assert "_1" in result.stem or "_2" in result.stem


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------


class TestStateTransitions:
    """Validates the app state machine initial state."""

    def test_initial_state_is_idle(self, app: Pcm2WavApp) -> None:
        """App starts in IDLE state."""
        # The state attribute name may vary; check common patterns
        state = getattr(app, "_state", None) or getattr(app, "state", None)
        assert state is not None
        # Convert to string for comparison regardless of enum vs string
        state_str = str(state).upper()
        assert "IDLE" in state_str


# ---------------------------------------------------------------------------
# Directory writable check
# ---------------------------------------------------------------------------


class TestDirectoryWritable:
    """Validates _is_directory_writable() helper function."""

    def test_writable_directory_returns_true(self, tmp_path: Path) -> None:
        """Writable directory should return True."""
        assert _is_directory_writable(tmp_path) is True

    def test_nonexistent_directory_returns_false(self, tmp_path: Path) -> None:
        """Non-existent directory should return False."""
        nonexistent = tmp_path / "does_not_exist"
        assert _is_directory_writable(nonexistent) is False

    def test_unwritable_directory_returns_false(self, tmp_path: Path) -> None:
        """Unwritable directory should return False."""
        with patch.object(Path, "write_bytes", side_effect=OSError("blocked")):
            assert _is_directory_writable(tmp_path) is False
