"""Tests for pcm2wav.converter — byte swap, signedness, validation, conversion."""

from __future__ import annotations

import struct
import threading
import wave
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from pcm2wav.converter import (
    batch_convert,
    convert_8bit_signedness,
    convert_pcm_to_wav,
    swap_byte_order,
    validate_pcm_file,
)
from pcm2wav.models import ByteOrder, PcmConversionError, PcmFormat

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


# ---------------------------------------------------------------------------
# swap_byte_order
# ---------------------------------------------------------------------------


class TestSwapByteOrder:
    """Validates byte-order swap for 8/16/24-bit sample widths."""

    def test_16bit_swap(self) -> None:
        """16-bit LE 0x0102 should become 0x0201 after swap."""
        data = bytes([0x01, 0x02, 0x03, 0x04])
        result = swap_byte_order(data, sample_width=2)
        assert result == bytes([0x02, 0x01, 0x04, 0x03])

    def test_24bit_swap(self) -> None:
        """24-bit LE [0x01,0x02,0x03] should become [0x03,0x02,0x01]."""
        data = bytes([0x01, 0x02, 0x03, 0x04, 0x05, 0x06])
        result = swap_byte_order(data, sample_width=3)
        assert result == bytes([0x03, 0x02, 0x01, 0x06, 0x05, 0x04])

    def test_8bit_noop(self) -> None:
        """8-bit data has no byte order; swap should be a no-op."""
        data = bytes([0x01, 0x02, 0x03])
        result = swap_byte_order(data, sample_width=1)
        assert result == data

    def test_empty_data(self) -> None:
        """Empty input should return empty output."""
        assert swap_byte_order(b"", sample_width=2) == b""

    def test_invalid_sample_width(self) -> None:
        """Unsupported sample_width (e.g. 4) should raise PcmConversionError."""
        with pytest.raises(PcmConversionError):
            swap_byte_order(b"\x00\x00\x00\x00", sample_width=4)


# ---------------------------------------------------------------------------
# convert_8bit_signedness
# ---------------------------------------------------------------------------


class TestConvert8bitSignedness:
    """Validates 8-bit signed-to-unsigned XOR 0x80 conversion."""

    def test_0x00_becomes_0x80(self) -> None:
        """Signed 0x00 (silence) maps to unsigned 0x80 (silence)."""
        assert convert_8bit_signedness(b"\x00") == b"\x80"

    def test_0x7f_becomes_0xff(self) -> None:
        """Signed 0x7F (max positive) maps to unsigned 0xFF."""
        assert convert_8bit_signedness(b"\x7f") == b"\xff"

    def test_0x80_becomes_0x00(self) -> None:
        """Signed 0x80 (min negative) maps to unsigned 0x00."""
        assert convert_8bit_signedness(b"\x80") == b"\x00"

    def test_0xff_becomes_0x7f(self) -> None:
        """Signed 0xFF (-1) maps to unsigned 0x7F."""
        assert convert_8bit_signedness(b"\xff") == b"\x7f"

    def test_full_range(self) -> None:
        """All 256 byte values should be correctly mapped via XOR 0x80."""
        data = bytes(range(256))
        result = convert_8bit_signedness(data)
        expected = bytes((b + 128) % 256 for b in range(256))
        assert result == expected


# ---------------------------------------------------------------------------
# validate_pcm_file
# ---------------------------------------------------------------------------


class TestValidatePcmFile:
    """Validates pre-conversion file checks."""

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        """Missing file should produce an error."""
        fake_path = tmp_path / "nonexistent.pcm"
        fmt = PcmFormat()
        errors, warnings = validate_pcm_file(fake_path, fmt)
        assert len(errors) >= 1
        assert len(warnings) == 0

    def test_empty_file(self, empty_pcm: Path) -> None:
        """Empty file should produce an error."""
        fmt = PcmFormat()
        errors, warnings = validate_pcm_file(empty_pcm, fmt)
        assert len(errors) >= 1

    def test_frame_misaligned(self, frame_misaligned_pcm: Path) -> None:
        """File not aligned to frame_size should produce a warning."""
        fmt = PcmFormat(bit_depth=16, channels=1)  # frame_size=2
        errors, warnings = validate_pcm_file(frame_misaligned_pcm, fmt)
        assert len(errors) == 0
        assert len(warnings) >= 1

    def test_valid_file(self, sine_wave_pcm_16bit: Path) -> None:
        """Valid file should produce no errors and no warnings."""
        fmt = PcmFormat(
            sample_rate=44100,
            bit_depth=16,
            channels=1,
        )
        errors, warnings = validate_pcm_file(sine_wave_pcm_16bit, fmt)
        assert errors == []
        assert warnings == []

    def test_4gb_limit(self, tmp_path: Path) -> None:
        """File size exceeding 4 GB should produce an error.

        Uses mock to avoid creating a real 4+ GB file.
        """
        fake_pcm = tmp_path / "huge.pcm"
        fake_pcm.write_bytes(b"\x00" * 100)  # small real file

        fmt = PcmFormat(bit_depth=16, channels=1)

        huge_size = 0xFFFF_FFFF + 1  # just over 4 GB

        class FakeStat:
            """Mock stat_result with overridden st_size."""

            st_size = huge_size

        with patch.object(type(fake_pcm), "stat", return_value=FakeStat()):
            errors, _warnings = validate_pcm_file(fake_pcm, fmt)

        assert len(errors) >= 1
        assert any("4GB" in e or "초과" in e for e in errors)


# ---------------------------------------------------------------------------
# convert_pcm_to_wav  (single file)
# ---------------------------------------------------------------------------


class TestConvertPcmToWav:
    """Validates single-file PCM-to-WAV conversion pipeline."""

    def test_16bit_le_mono(
        self,
        sine_wave_pcm_16bit: Path,
        tmp_path: Path,
    ) -> None:
        """16-bit LE mono conversion should produce valid WAV."""
        wav_path = tmp_path / "output.wav"
        fmt = PcmFormat(
            sample_rate=44100,
            bit_depth=16,
            channels=1,
        )
        result = convert_pcm_to_wav(sine_wave_pcm_16bit, wav_path, fmt)

        assert result.success is True
        assert wav_path.exists()

        with wave.open(str(wav_path), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 44100
            assert wf.getnframes() == 44100  # 1 second

    def test_16bit_be_mono(
        self,
        make_pcm_file: Callable[[bytes, str], Path],
        tmp_path: Path,
    ) -> None:
        """16-bit big-endian input should be byte-swapped in output WAV."""
        # Create 4 samples in big-endian: 0x0100, 0x0200, 0x0300, 0x0400
        be_data = struct.pack(">4h", 256, 512, 768, 1024)
        pcm_path = make_pcm_file(be_data, "be_16bit.pcm")
        wav_path = tmp_path / "be_output.wav"
        fmt = PcmFormat(
            sample_rate=8000,
            bit_depth=16,
            channels=1,
            byte_order=ByteOrder.BIG_ENDIAN,
        )

        result = convert_pcm_to_wav(pcm_path, wav_path, fmt)
        assert result.success is True

        with wave.open(str(wav_path), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            raw_frames = wf.readframes(4)

        # WAV stores LE; verify swapped values match original values
        values = struct.unpack("<4h", raw_frames)
        assert values == (256, 512, 768, 1024)

    def test_8bit_signed(
        self,
        make_pcm_file: Callable[[bytes, str], Path],
        tmp_path: Path,
    ) -> None:
        """8-bit signed input should be converted to unsigned in WAV."""
        # Signed: 0x00 (silence), 0x7F (max pos), 0x80 (min neg), 0xFF (-1)
        signed_data = bytes([0x00, 0x7F, 0x80, 0xFF])
        pcm_path = make_pcm_file(signed_data, "signed_8bit.pcm")
        wav_path = tmp_path / "signed_output.wav"
        fmt = PcmFormat(
            sample_rate=8000,
            bit_depth=8,
            channels=1,
            signed=True,
        )

        result = convert_pcm_to_wav(pcm_path, wav_path, fmt)
        assert result.success is True

        with wave.open(str(wav_path), "rb") as wf:
            raw_frames = wf.readframes(4)

        # After XOR 0x80: 0x80, 0xFF, 0x00, 0x7F
        assert raw_frames == bytes([0x80, 0xFF, 0x00, 0x7F])

    def test_8bit_unsigned(
        self,
        make_pcm_file: Callable[[bytes, str], Path],
        tmp_path: Path,
    ) -> None:
        """8-bit unsigned input should pass through without conversion."""
        unsigned_data = bytes([0x80, 0xFF, 0x00, 0x7F])
        pcm_path = make_pcm_file(unsigned_data, "unsigned_8bit.pcm")
        wav_path = tmp_path / "unsigned_output.wav"
        fmt = PcmFormat(
            sample_rate=8000,
            bit_depth=8,
            channels=1,
            signed=False,
        )

        result = convert_pcm_to_wav(pcm_path, wav_path, fmt)
        assert result.success is True

        with wave.open(str(wav_path), "rb") as wf:
            raw_frames = wf.readframes(4)

        # No conversion; data passes through unchanged
        assert raw_frames == unsigned_data

    def test_24bit_le_stereo(
        self,
        make_pcm_file: Callable[[bytes, str], Path],
        tmp_path: Path,
    ) -> None:
        """24-bit LE stereo conversion should produce valid WAV."""
        # 2 frames of 24-bit stereo = 2 * 3 * 2 = 12 bytes
        # Frame 1: L=[0x01,0x02,0x03] R=[0x04,0x05,0x06]
        # Frame 2: L=[0x07,0x08,0x09] R=[0x0A,0x0B,0x0C]
        pcm_data = bytes(
            [
                0x01,
                0x02,
                0x03,
                0x04,
                0x05,
                0x06,
                0x07,
                0x08,
                0x09,
                0x0A,
                0x0B,
                0x0C,
            ]
        )
        pcm_path = make_pcm_file(pcm_data, "24bit_stereo.pcm")
        wav_path = tmp_path / "24bit_stereo.wav"
        fmt = PcmFormat(
            sample_rate=48000,
            bit_depth=24,
            channels=2,
        )

        result = convert_pcm_to_wav(pcm_path, wav_path, fmt)
        assert result.success is True

        with wave.open(str(wav_path), "rb") as wf:
            assert wf.getnchannels() == 2
            assert wf.getsampwidth() == 3
            assert wf.getframerate() == 48000
            assert wf.getnframes() == 2

    def test_wav_header_fields(
        self,
        sine_wave_pcm_16bit: Path,
        tmp_path: Path,
    ) -> None:
        """WAV header fields should match PcmFormat parameters exactly."""
        wav_path = tmp_path / "header_check.wav"
        fmt = PcmFormat(
            sample_rate=44100,
            bit_depth=16,
            channels=1,
        )

        convert_pcm_to_wav(sine_wave_pcm_16bit, wav_path, fmt)

        with wave.open(str(wav_path), "rb") as wf:
            assert wf.getnchannels() == fmt.channels
            assert wf.getsampwidth() == fmt.sample_width
            assert wf.getframerate() == fmt.sample_rate
            expected_frames = sine_wave_pcm_16bit.stat().st_size // fmt.frame_size
            assert wf.getnframes() == expected_frames

    def test_nonexistent_input(self, tmp_path: Path) -> None:
        """Missing input file should raise PcmConversionError."""
        fake_input = tmp_path / "no_such_file.pcm"
        wav_path = tmp_path / "output.wav"
        fmt = PcmFormat()

        with pytest.raises(PcmConversionError):
            convert_pcm_to_wav(fake_input, wav_path, fmt)

    def test_empty_file(self, empty_pcm: Path, tmp_path: Path) -> None:
        """Empty input file should raise PcmConversionError."""
        wav_path = tmp_path / "output.wav"
        fmt = PcmFormat()

        with pytest.raises(PcmConversionError):
            convert_pcm_to_wav(empty_pcm, wav_path, fmt)

    def test_cancel_deletes_partial(
        self,
        make_pcm_file: Callable[[bytes, str], Path],
        tmp_path: Path,
    ) -> None:
        """Setting cancel_event should delete partial output file."""
        # Create a file large enough to span multiple chunks
        pcm_data = b"\x00" * (262_144 * 3)  # 3x CHUNK_SIZE
        pcm_path = make_pcm_file(pcm_data, "large.pcm")
        wav_path = tmp_path / "cancelled.wav"
        fmt = PcmFormat(
            sample_rate=44100,
            bit_depth=16,
            channels=1,
        )

        cancel_event = threading.Event()
        # Set cancel before conversion so it cancels on first check
        cancel_event.set()

        result = convert_pcm_to_wav(
            pcm_path,
            wav_path,
            fmt,
            cancel_event=cancel_event,
        )

        assert result.success is False
        assert not wav_path.exists()

    def test_progress_callback_called(
        self,
        sine_wave_pcm_16bit: Path,
        tmp_path: Path,
    ) -> None:
        """Progress callback should be invoked at least once."""
        wav_path = tmp_path / "progress.wav"
        fmt = PcmFormat(
            sample_rate=44100,
            bit_depth=16,
            channels=1,
        )
        calls: list[tuple[int, int]] = []

        def on_progress(bytes_processed: int, total_bytes: int) -> None:
            calls.append((bytes_processed, total_bytes))

        convert_pcm_to_wav(
            sine_wave_pcm_16bit,
            wav_path,
            fmt,
            progress_callback=on_progress,
        )

        assert len(calls) >= 1
        # Last call should have bytes_processed == total_bytes
        last_processed, total = calls[-1]
        assert last_processed == total

    def test_one_frame_file(
        self,
        one_frame_16bit_mono: Path,
        tmp_path: Path,
    ) -> None:
        """Single-frame file should convert successfully."""
        wav_path = tmp_path / "one_frame.wav"
        fmt = PcmFormat(
            sample_rate=44100,
            bit_depth=16,
            channels=1,
        )

        result = convert_pcm_to_wav(one_frame_16bit_mono, wav_path, fmt)
        assert result.success is True
        assert result.frames_written == 1

        with wave.open(str(wav_path), "rb") as wf:
            assert wf.getnframes() == 1

    def test_chunk_boundary_file(
        self,
        chunk_boundary_pcm: Path,
        tmp_path: Path,
    ) -> None:
        """File exactly at CHUNK_SIZE boundary should convert successfully."""
        wav_path = tmp_path / "chunk_boundary.wav"
        fmt = PcmFormat(
            sample_rate=44100,
            bit_depth=16,
            channels=1,
        )

        result = convert_pcm_to_wav(chunk_boundary_pcm, wav_path, fmt)
        assert result.success is True

        expected_frames = 262_144 // fmt.frame_size
        assert result.frames_written == expected_frames


# ---------------------------------------------------------------------------
# batch_convert
# ---------------------------------------------------------------------------


class TestBatchConvert:
    """Validates multi-file batch conversion."""

    def test_multiple_success(
        self,
        make_pcm_file: Callable[[bytes, str], Path],
        tmp_path: Path,
    ) -> None:
        """All valid files should convert successfully."""
        fmt = PcmFormat(sample_rate=8000, bit_depth=16, channels=1)
        pcm_data = struct.pack("<4h", 100, 200, 300, 400)

        files: list[tuple[Path, Path]] = []
        for i in range(3):
            pcm_path = make_pcm_file(pcm_data, f"batch_{i}.pcm")
            wav_path = tmp_path / f"batch_{i}.wav"
            files.append((pcm_path, wav_path))

        results = batch_convert(files, fmt)

        assert len(results) == 3
        assert all(r.success for r in results)
        for _, wav_path in files:
            assert wav_path.exists()

    def test_partial_failure_continues(
        self,
        make_pcm_file: Callable[[bytes, str], Path],
        tmp_path: Path,
    ) -> None:
        """One bad file should not stop conversion of remaining files."""
        fmt = PcmFormat(sample_rate=8000, bit_depth=16, channels=1)
        good_data = struct.pack("<2h", 100, 200)

        good1 = make_pcm_file(good_data, "good1.pcm")
        bad_path = tmp_path / "nonexistent.pcm"  # does not exist
        good2 = make_pcm_file(good_data, "good2.pcm")

        files: list[tuple[Path, Path]] = [
            (good1, tmp_path / "good1.wav"),
            (bad_path, tmp_path / "bad.wav"),
            (good2, tmp_path / "good2.wav"),
        ]

        results = batch_convert(files, fmt)

        assert len(results) == 3
        assert results[0].success is True
        assert results[1].success is False
        assert results[2].success is True

    def test_cancel_stops_batch(
        self,
        make_pcm_file: Callable[[bytes, str], Path],
        tmp_path: Path,
    ) -> None:
        """Setting cancel_event should stop processing remaining files."""
        fmt = PcmFormat(sample_rate=8000, bit_depth=16, channels=1)
        pcm_data = struct.pack("<2h", 100, 200)

        files: list[tuple[Path, Path]] = []
        for i in range(5):
            pcm_path = make_pcm_file(pcm_data, f"cancel_{i}.pcm")
            wav_path = tmp_path / f"cancel_{i}.wav"
            files.append((pcm_path, wav_path))

        cancel_event = threading.Event()

        call_count = 0

        def progress_and_cancel(
            file_index: int,
            total_files: int,
            bytes_done: int,
            bytes_total: int,
        ) -> None:
            nonlocal call_count
            call_count += 1
            # Cancel after first file completes
            if file_index >= 1:
                cancel_event.set()

        results = batch_convert(
            files,
            fmt,
            progress_callback=progress_and_cancel,
            cancel_event=cancel_event,
        )

        # Should have fewer results than total files
        assert len(results) < len(files)

    def test_progress_callback(
        self,
        make_pcm_file: Callable[[bytes, str], Path],
        tmp_path: Path,
    ) -> None:
        """Batch progress callback should receive correct arguments."""
        fmt = PcmFormat(sample_rate=8000, bit_depth=16, channels=1)
        pcm_data = struct.pack("<2h", 100, 200)

        files: list[tuple[Path, Path]] = []
        for i in range(2):
            pcm_path = make_pcm_file(pcm_data, f"prog_{i}.pcm")
            wav_path = tmp_path / f"prog_{i}.wav"
            files.append((pcm_path, wav_path))

        calls: list[tuple[int, int, int, int]] = []

        def on_progress(
            file_index: int,
            total_files: int,
            bytes_done: int,
            bytes_total: int,
        ) -> None:
            calls.append((file_index, total_files, bytes_done, bytes_total))

        batch_convert(files, fmt, progress_callback=on_progress)

        assert len(calls) >= 2  # at least one per file
        # All calls should report total_files=2
        assert all(c[1] == 2 for c in calls)
        # file_index should be 0-based
        file_indices = {c[0] for c in calls}
        assert 0 in file_indices
        assert 1 in file_indices

    def test_empty_file_list(self) -> None:
        """Empty file list should return empty results."""
        fmt = PcmFormat()
        results = batch_convert([], fmt)
        assert results == []
