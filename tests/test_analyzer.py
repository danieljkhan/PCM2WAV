"""Tests for pcm2wav.analyzer -- PCM format auto-detection."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import TYPE_CHECKING

import pytest

from pcm2wav.analyzer import analyze_pcm_file
from pcm2wav.models import FormatCandidate, PcmFormat

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# TestAnalyzePcmFile
# ---------------------------------------------------------------------------


class TestAnalyzePcmFile:
    """Validates PCM format auto-detection across various audio formats."""

    def test_detects_16bit_mono_16khz(
        self,
        mono_16bit_16khz_pcm: Path,
    ) -> None:
        """16-bit mono 16 kHz speech file should be detected correctly.

        Top candidate should have bit_depth=16 and channels=1.
        Sample rate 16000 should appear among the candidates, and
        the matching preset should be 'Wideband Telephony'.
        """
        candidates = analyze_pcm_file(mono_16bit_16khz_pcm)

        assert len(candidates) > 0
        top = candidates[0]
        assert top.fmt.bit_depth == 16
        assert top.fmt.channels == 1

        # 16000 Hz should appear among candidates
        rates = {c.fmt.sample_rate for c in candidates}
        assert 16000 in rates

        # Find the 16 kHz candidate and check preset
        matching = [
            c
            for c in candidates
            if c.fmt.sample_rate == 16000 and c.fmt.bit_depth == 16 and c.fmt.channels == 1
        ]
        assert len(matching) > 0
        wideband = matching[0]
        assert wideband.preset_name == "Wideband Telephony (16000Hz, 16-bit, Mono)"

    def test_detects_stereo_44100(
        self,
        stereo_16bit_44100_pcm: Path,
    ) -> None:
        """Stereo 44100 Hz file should be detected as 16-bit stereo.

        Top candidate should have bit_depth=16 and channels=2.
        44100 Hz should appear among the candidates.
        """
        candidates = analyze_pcm_file(stereo_16bit_44100_pcm)

        assert len(candidates) > 0
        top = candidates[0]
        assert top.fmt.bit_depth == 16
        assert top.fmt.channels == 2

        rates = {c.fmt.sample_rate for c in candidates}
        assert 44100 in rates

    def test_detects_8bit_unsigned(
        self,
        mono_8bit_unsigned_pcm: Path,
    ) -> None:
        """8-bit unsigned mono file should be detected as 8-bit."""
        candidates = analyze_pcm_file(mono_8bit_unsigned_pcm)

        assert len(candidates) > 0
        top = candidates[0]
        assert top.fmt.bit_depth == 8

    def test_returns_sorted_by_confidence(
        self,
        mono_16bit_16khz_pcm: Path,
    ) -> None:
        """Results should be sorted in descending order by confidence."""
        candidates = analyze_pcm_file(mono_16bit_16khz_pcm)

        assert len(candidates) > 0
        confidences = [c.confidence for c in candidates]
        for i in range(len(confidences) - 1):
            assert confidences[i] >= confidences[i + 1], (
                f"Candidate {i} (confidence={confidences[i]}) should have "
                f">= confidence than candidate {i + 1} "
                f"(confidence={confidences[i + 1]})"
            )

    def test_max_candidates_limits_results(
        self,
        mono_16bit_16khz_pcm: Path,
    ) -> None:
        """max_candidates parameter should limit the number of results."""
        candidates = analyze_pcm_file(
            mono_16bit_16khz_pcm,
            max_candidates=2,
        )
        assert len(candidates) <= 2

    def test_empty_file_raises(self, tmp_path: Path) -> None:
        """Empty file should return empty list (file too small)."""
        empty_file = tmp_path / "empty.pcm"
        empty_file.write_bytes(b"")

        # analyze_pcm_file calls stat() on 0-byte file; it returns []
        # for files below _MIN_USEFUL_BYTES, but stat() on empty file
        # should not crash. The function returns [] for tiny files.
        result = analyze_pcm_file(empty_file)
        assert result == []

    def test_tiny_file_handles_gracefully(self, tmp_path: Path) -> None:
        """3-byte file should not crash; returns empty or valid candidates."""
        tiny_file = tmp_path / "tiny.pcm"
        tiny_file.write_bytes(b"\x01\x02\x03")

        # Should not raise; may return empty list or valid candidates
        result = analyze_pcm_file(tiny_file)
        assert isinstance(result, list)

    def test_existing_sine_wave_detection(
        self,
        sine_wave_pcm_16bit: Path,
    ) -> None:
        """Existing 440 Hz sine fixture should be detected as 16-bit mono.

        The analyzer should return at least one candidate with
        bit_depth=16 and channels=1 with reasonable confidence.
        """
        candidates = analyze_pcm_file(sine_wave_pcm_16bit)

        assert len(candidates) > 0
        # Find a 16-bit mono candidate
        matching = [c for c in candidates if c.fmt.bit_depth == 16 and c.fmt.channels == 1]
        assert len(matching) > 0, "Expected at least one 16-bit mono candidate"
        best_match = matching[0]
        assert best_match.confidence > 0.0

    def test_preset_matching(
        self,
        mono_16bit_16khz_pcm: Path,
    ) -> None:
        """When detected format matches a preset, preset_name is populated."""
        candidates = analyze_pcm_file(mono_16bit_16khz_pcm)

        # Find candidates that have a preset_name set
        with_preset = [c for c in candidates if c.preset_name is not None]
        assert len(with_preset) > 0, "At least one candidate should match a known preset"
        # The preset name should be a non-empty string
        for c in with_preset:
            assert isinstance(c.preset_name, str)
            assert len(c.preset_name) > 0


# ---------------------------------------------------------------------------
# TestFormatCandidate
# ---------------------------------------------------------------------------


class TestFormatCandidate:
    """Validates FormatCandidate dataclass properties."""

    def test_format_candidate_creation(self) -> None:
        """FormatCandidate can be created with all fields."""
        fmt = PcmFormat(
            sample_rate=44100,
            bit_depth=16,
            channels=1,
        )
        candidate = FormatCandidate(
            fmt=fmt,
            confidence=0.85,
            preset_name="CD Quality Mono (44100Hz, 16-bit, Mono)",
            reason="bit_depth=16(0.80), ch=1(0.65)",
        )
        assert candidate.fmt == fmt
        assert candidate.confidence == 0.85
        assert candidate.preset_name == ("CD Quality Mono (44100Hz, 16-bit, Mono)")
        assert "bit_depth=16" in candidate.reason

    def test_format_candidate_frozen(self) -> None:
        """FormatCandidate should be immutable (frozen dataclass)."""
        fmt = PcmFormat(sample_rate=8000, bit_depth=16, channels=1)
        candidate = FormatCandidate(
            fmt=fmt,
            confidence=0.5,
            reason="test",
        )
        with pytest.raises(FrozenInstanceError):
            candidate.confidence = 0.9  # type: ignore[misc]
