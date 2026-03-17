"""Tests for pcm2wav.presets — preset definitions and validation."""

from __future__ import annotations

from pcm2wav.models import PcmFormat
from pcm2wav.presets import DEFAULT_PRESET_NAME, PRESETS


class TestPresets:
    """Validates preset dictionary structure and content."""

    def test_all_presets_valid_pcm_format(self) -> None:
        """Every non-None preset value must be a valid PcmFormat instance."""
        for name, fmt in PRESETS.items():
            if fmt is not None:
                assert isinstance(fmt, PcmFormat), f"Preset '{name}' is not a PcmFormat instance"

    def test_custom_is_none(self) -> None:
        """The 'Custom' preset must be None (signals manual input mode)."""
        assert "Custom" in PRESETS
        assert PRESETS["Custom"] is None

    def test_default_preset_exists(self) -> None:
        """DEFAULT_PRESET_NAME must exist as a key in PRESETS."""
        assert DEFAULT_PRESET_NAME in PRESETS

    def test_default_preset_not_none(self) -> None:
        """The default preset must have a valid PcmFormat (not None)."""
        assert PRESETS[DEFAULT_PRESET_NAME] is not None

    def test_dict_order_preserved(self) -> None:
        """First key should be CD Quality Stereo; last key should be Custom."""
        keys = list(PRESETS.keys())
        assert keys[0] == "CD Quality (44100Hz, 16-bit, Stereo)"
        assert keys[-1] == "Custom"

    def test_preset_count(self) -> None:
        """There should be exactly 8 presets (7 named + Custom)."""
        assert len(PRESETS) == 8
