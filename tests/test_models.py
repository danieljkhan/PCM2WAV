"""Tests for pcm2wav.models — PcmFormat validation and ConversionResult."""

from __future__ import annotations

from pathlib import Path

import pytest

from pcm2wav.models import (
    MAX_SAMPLE_RATE,
    MIN_SAMPLE_RATE,
    ByteOrder,
    ConversionResult,
    PcmFormat,
)


class TestPcmFormat:
    """Validates PcmFormat construction, computed properties, and constraints."""

    # -- Default values -------------------------------------------------------

    def test_default_values(self) -> None:
        """Default PcmFormat should be 44100 Hz, 16-bit, mono, LE, signed."""
        fmt = PcmFormat()
        assert fmt.sample_rate == 44100
        assert fmt.bit_depth == 16
        assert fmt.channels == 1
        assert fmt.byte_order is ByteOrder.LITTLE_ENDIAN
        assert fmt.signed is True

    # -- sample_width ---------------------------------------------------------

    def test_sample_width_16bit(self) -> None:
        """16-bit depth yields sample_width of 2 bytes."""
        fmt = PcmFormat(bit_depth=16)
        assert fmt.sample_width == 2

    def test_sample_width_24bit(self) -> None:
        """24-bit depth yields sample_width of 3 bytes."""
        fmt = PcmFormat(bit_depth=24)
        assert fmt.sample_width == 3

    def test_sample_width_8bit(self) -> None:
        """8-bit depth yields sample_width of 1 byte."""
        fmt = PcmFormat(bit_depth=8)
        assert fmt.sample_width == 1

    # -- frame_size -----------------------------------------------------------

    def test_frame_size_mono(self) -> None:
        """Mono 16-bit: frame_size = 2 bytes."""
        fmt = PcmFormat(bit_depth=16, channels=1)
        assert fmt.frame_size == 2

    def test_frame_size_stereo(self) -> None:
        """Stereo 16-bit: frame_size = 4 bytes."""
        fmt = PcmFormat(bit_depth=16, channels=2)
        assert fmt.frame_size == 4

    # -- Validation errors ----------------------------------------------------

    def test_invalid_bit_depth(self) -> None:
        """32-bit is not supported in v1; must raise ValueError."""
        with pytest.raises(ValueError, match="bit_depth"):
            PcmFormat(bit_depth=32)

    def test_sample_rate_too_low(self) -> None:
        """sample_rate=0 is below minimum; must raise ValueError."""
        with pytest.raises(ValueError, match="sample_rate"):
            PcmFormat(sample_rate=0)

    def test_sample_rate_too_high(self) -> None:
        """sample_rate=384001 exceeds maximum; must raise ValueError."""
        with pytest.raises(ValueError, match="sample_rate"):
            PcmFormat(sample_rate=384_001)

    def test_invalid_channels(self) -> None:
        """channels=3 is not supported; must raise ValueError."""
        with pytest.raises(ValueError, match="channels"):
            PcmFormat(channels=3)

    def test_unsigned_16bit_rejected(self) -> None:
        """16-bit unsigned violates WAV standard; must raise ValueError."""
        with pytest.raises(ValueError, match="unsigned"):
            PcmFormat(bit_depth=16, signed=False)

    def test_unsigned_24bit_rejected(self) -> None:
        """24-bit unsigned violates WAV standard; must raise ValueError."""
        with pytest.raises(ValueError, match="unsigned"):
            PcmFormat(bit_depth=24, signed=False)

    # -- Valid edge cases -----------------------------------------------------

    def test_8bit_unsigned_allowed(self) -> None:
        """8-bit unsigned is valid per WAV standard."""
        fmt = PcmFormat(bit_depth=8, signed=False)
        assert fmt.bit_depth == 8
        assert fmt.signed is False

    def test_8bit_signed_allowed(self) -> None:
        """8-bit signed is valid (converter handles sign conversion)."""
        fmt = PcmFormat(bit_depth=8, signed=True)
        assert fmt.bit_depth == 8
        assert fmt.signed is True

    def test_min_sample_rate(self) -> None:
        """Minimum sample_rate (1) must be accepted."""
        fmt = PcmFormat(sample_rate=MIN_SAMPLE_RATE)
        assert fmt.sample_rate == 1

    def test_max_sample_rate(self) -> None:
        """Maximum sample_rate (384000) must be accepted."""
        fmt = PcmFormat(sample_rate=MAX_SAMPLE_RATE)
        assert fmt.sample_rate == 384_000

    def test_big_endian(self) -> None:
        """Big-endian byte order must be accepted."""
        fmt = PcmFormat(byte_order=ByteOrder.BIG_ENDIAN)
        assert fmt.byte_order is ByteOrder.BIG_ENDIAN


class TestConversionResult:
    """Validates ConversionResult dataclass behaviour."""

    def test_default_fields(self) -> None:
        """Optional fields should have correct default values."""
        result = ConversionResult(
            input_path=Path("input.pcm"),
            output_path=None,
            success=False,
        )
        assert result.error_message is None
        assert result.elapsed_seconds == 0.0
        assert result.frames_written == 0
        assert result.output_size_bytes == 0

    def test_mutable(self) -> None:
        """ConversionResult is mutable — fields can be updated after init."""
        result = ConversionResult(
            input_path=Path("input.pcm"),
            output_path=Path("output.wav"),
            success=False,
        )
        result.success = True
        result.frames_written = 44100
        result.elapsed_seconds = 1.5
        result.output_size_bytes = 88244

        assert result.success is True
        assert result.frames_written == 44100
        assert result.elapsed_seconds == 1.5
        assert result.output_size_bytes == 88244
