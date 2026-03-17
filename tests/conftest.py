"""Test fixtures for PCM2WAV test suite.

Provides known-pattern PCM test files for deterministic conversion testing.
All fixtures generate files in pytest's ``tmp_path`` temporary directory.
"""

from __future__ import annotations

import math
import struct
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

# Matches the CHUNK_SIZE constant defined in converter.py.
CHUNK_SIZE: int = 262_144


@pytest.fixture()
def tmp_dir(tmp_path: Path) -> Path:
    """Return a temporary directory (alias for ``tmp_path``)."""
    return tmp_path


@pytest.fixture()
def make_pcm_file(tmp_path: Path) -> Callable[[bytes, str], Path]:
    """Factory fixture: write arbitrary bytes to a named temp PCM file.

    Returns:
        A callable ``(data, filename) -> Path`` that creates the file and
        returns its absolute path.
    """

    def _make(data: bytes, filename: str) -> Path:
        path = tmp_path / filename
        path.write_bytes(data)
        return path

    return _make


@pytest.fixture()
def sine_wave_pcm_16bit(tmp_path: Path) -> Path:
    """440 Hz sine wave, 1 second, 44100 Hz, 16-bit, mono, LE, signed.

    Generates 44100 samples of a 440 Hz sine wave packed as signed
    16-bit little-endian integers.
    """
    sample_rate = 44100
    frequency = 440.0
    duration_seconds = 1.0
    num_samples = int(sample_rate * duration_seconds)
    amplitude = 32767  # max for signed 16-bit

    samples: list[bytes] = []
    for i in range(num_samples):
        value = int(amplitude * math.sin(2.0 * math.pi * frequency * i / sample_rate))
        samples.append(struct.pack("<h", value))

    pcm_data = b"".join(samples)
    path = tmp_path / "sine_440hz_16bit_mono.pcm"
    path.write_bytes(pcm_data)
    return path


@pytest.fixture()
def incrementing_bytes_pcm(tmp_path: Path) -> Path:
    """0x00-0xFF repeated pattern (256 bytes total)."""
    pcm_data = bytes(range(256))
    path = tmp_path / "incrementing_bytes.pcm"
    path.write_bytes(pcm_data)
    return path


@pytest.fixture()
def all_zeros_pcm(tmp_path: Path) -> Path:
    """All 0x00 bytes (256 bytes)."""
    pcm_data = b"\x00" * 256
    path = tmp_path / "all_zeros.pcm"
    path.write_bytes(pcm_data)
    return path


@pytest.fixture()
def all_ff_pcm(tmp_path: Path) -> Path:
    """All 0xFF bytes (256 bytes)."""
    pcm_data = b"\xff" * 256
    path = tmp_path / "all_ff.pcm"
    path.write_bytes(pcm_data)
    return path


@pytest.fixture()
def one_frame_16bit_mono(tmp_path: Path) -> Path:
    """Exactly 1 frame (2 bytes) of 16-bit mono PCM."""
    pcm_data = struct.pack("<h", 1000)  # arbitrary sample value
    path = tmp_path / "one_frame_16bit_mono.pcm"
    path.write_bytes(pcm_data)
    return path


@pytest.fixture()
def chunk_boundary_pcm(tmp_path: Path) -> Path:
    """Exactly CHUNK_SIZE (262144) bytes of repeating pattern."""
    pattern = bytes(range(256))
    repetitions = CHUNK_SIZE // len(pattern)
    pcm_data = pattern * repetitions
    assert len(pcm_data) == CHUNK_SIZE
    path = tmp_path / "chunk_boundary.pcm"
    path.write_bytes(pcm_data)
    return path


@pytest.fixture()
def frame_misaligned_pcm(tmp_path: Path) -> Path:
    """Not a multiple of frame_size for 16-bit mono (frame_size=2).

    101 bytes = 50 complete frames + 1 extra byte.
    """
    pcm_data = bytes(range(101))
    path = tmp_path / "frame_misaligned.pcm"
    path.write_bytes(pcm_data)
    return path


@pytest.fixture()
def mono_16bit_16khz_pcm(tmp_path: Path) -> Path:
    """16-bit LE signed mono at 16000 Hz, 1-second 400 Hz sine wave.

    Simulates KsponSpeech-like speech format (32000 bytes total).
    """
    sample_rate = 16000
    frequency = 400.0
    num_samples = sample_rate  # 1 second
    amplitude = 16384  # moderate volume

    samples: list[bytes] = []
    for i in range(num_samples):
        value = int(amplitude * math.sin(2.0 * math.pi * frequency * i / sample_rate))
        samples.append(struct.pack("<h", value))

    pcm_data = b"".join(samples)
    path = tmp_path / "mono_16bit_16khz.pcm"
    path.write_bytes(pcm_data)
    return path


@pytest.fixture()
def stereo_16bit_44100_pcm(tmp_path: Path) -> Path:
    """16-bit LE signed stereo at 44100 Hz, 1-second sine wave.

    Both L/R channels contain the same 440 Hz sine wave (correlated).
    Total size: 44100 * 2 channels * 2 bytes = 176400 bytes.
    """
    sample_rate = 44100
    frequency = 440.0
    num_samples = sample_rate  # 1 second
    amplitude = 24000

    samples: list[bytes] = []
    for i in range(num_samples):
        value = int(amplitude * math.sin(2.0 * math.pi * frequency * i / sample_rate))
        packed = struct.pack("<h", value)
        samples.append(packed)  # Left channel
        samples.append(packed)  # Right channel (same = correlated)

    pcm_data = b"".join(samples)
    path = tmp_path / "stereo_16bit_44100.pcm"
    path.write_bytes(pcm_data)
    return path


@pytest.fixture()
def mono_8bit_unsigned_pcm(tmp_path: Path) -> Path:
    """8-bit unsigned mono at 8000 Hz, 1-second sine wave.

    Values centered around 128 (unsigned silence).
    Total size: 8000 bytes.
    """
    sample_rate = 8000
    frequency = 400.0
    num_samples = sample_rate  # 1 second
    amplitude = 80  # moderate volume within 0-255 range

    samples: list[bytes] = []
    for i in range(num_samples):
        value = int(128 + amplitude * math.sin(2.0 * math.pi * frequency * i / sample_rate))
        samples.append(struct.pack("B", max(0, min(255, value))))

    pcm_data = b"".join(samples)
    path = tmp_path / "mono_8bit_unsigned.pcm"
    path.write_bytes(pcm_data)
    return path


@pytest.fixture()
def empty_pcm(tmp_path: Path) -> Path:
    """Empty file (0 bytes)."""
    path = tmp_path / "empty.pcm"
    path.write_bytes(b"")
    return path
