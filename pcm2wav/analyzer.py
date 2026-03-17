"""PCM 포맷 자동 감지 모듈.

원시 PCM 파일의 바이트 통계를 분석하여 가능한 포맷 후보를 추론한다.
GUI 및 converter와 독립적으로 동작하며, models와 presets만 참조한다.
"""

from __future__ import annotations

import logging
import math
import struct
from typing import TYPE_CHECKING

from pcm2wav.models import ByteOrder, FormatCandidate, PcmFormat
from pcm2wav.presets import PRESETS

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_ANALYSIS_BYTES: int = 1_048_576  # 1 MB
_MIN_USEFUL_BYTES: int = 4
_CANDIDATE_BIT_DEPTHS: list[int] = [8, 16, 24]
_CANDIDATE_CHANNELS: list[int] = [1, 2]
_CANDIDATE_SAMPLE_RATES: list[int] = [8000, 11025, 16000, 22050, 44100, 48000]
_SCORE_THRESHOLD: float = 0.15
_COMMON_RATE_PRIOR: dict[int, float] = {
    8000: 1.05,
    16000: 1.10,
    22050: 1.02,
    44100: 1.15,
    48000: 1.12,
}


def analyze_pcm_file(
    pcm_path: Path,
    max_candidates: int = 5,
) -> list[FormatCandidate]:
    """PCM 파일을 분석하여 가능한 포맷 후보 목록을 반환한다.

    Args:
        pcm_path: 분석할 PCM 파일 경로.
        max_candidates: 반환할 최대 후보 수.

    Returns:
        신뢰도 내림차순으로 정렬된 FormatCandidate 리스트.
    """
    file_size = pcm_path.stat().st_size
    if file_size < _MIN_USEFUL_BYTES:
        logger.debug("File too small for analysis: %d bytes", file_size)
        return []

    with open(pcm_path, "rb") as f:
        raw_data = f.read(_MAX_ANALYSIS_BYTES)

    candidates: list[FormatCandidate] = []

    # Phase 1: score bit depths
    bit_depth_scores: dict[int, float] = {}
    for bd in _CANDIDATE_BIT_DEPTHS:
        score = _score_bit_depth(raw_data, bd, file_size)
        if score > _SCORE_THRESHOLD:
            bit_depth_scores[bd] = score

    if not bit_depth_scores:
        logger.debug("No bit depth scored above threshold")
        return []

    # Phase 2: for each surviving bit depth, score channels
    bd_ch_scores: list[tuple[int, int, float, float]] = []
    for bd, bd_score in bit_depth_scores.items():
        for ch in _CANDIDATE_CHANNELS:
            ch_score = _score_channels(raw_data, bd, ch, file_size)
            if ch_score > _SCORE_THRESHOLD:
                bd_ch_scores.append((bd, ch, bd_score, ch_score))

    if not bd_ch_scores:
        logger.debug("No bit-depth/channel combo scored above threshold")
        return []

    # Phase 3: score byte order for each combo
    bd_ch_bo_scores: list[tuple[int, int, ByteOrder, float, float, float]] = []
    for bd, ch, bd_score, ch_score in bd_ch_scores:
        if bd == 8:
            # 8-bit has no byte order distinction
            bd_ch_bo_scores.append((bd, ch, ByteOrder.LITTLE_ENDIAN, bd_score, ch_score, 1.0))
        else:
            le_score = _score_byte_order(raw_data, bd, ByteOrder.LITTLE_ENDIAN)
            be_score = _score_byte_order(raw_data, bd, ByteOrder.BIG_ENDIAN)
            # Keep the better one, or both if close
            if le_score >= be_score:
                bd_ch_bo_scores.append(
                    (bd, ch, ByteOrder.LITTLE_ENDIAN, bd_score, ch_score, le_score)
                )
                if be_score > _SCORE_THRESHOLD and be_score >= le_score * 0.8:
                    bd_ch_bo_scores.append(
                        (bd, ch, ByteOrder.BIG_ENDIAN, bd_score, ch_score, be_score)
                    )
            else:
                bd_ch_bo_scores.append((bd, ch, ByteOrder.BIG_ENDIAN, bd_score, ch_score, be_score))
                if le_score > _SCORE_THRESHOLD and le_score >= be_score * 0.8:
                    bd_ch_bo_scores.append(
                        (
                            bd,
                            ch,
                            ByteOrder.LITTLE_ENDIAN,
                            bd_score,
                            ch_score,
                            le_score,
                        )
                    )

    # Phase 4: score sample rates and signedness, build candidates
    for bd, ch, bo, bd_score, ch_score, bo_score in bd_ch_bo_scores:
        # Score signedness (only matters for 8-bit)
        for signed in [True, False] if bd == 8 else [True]:
            sign_score = _score_signedness(raw_data, bd, signed)

            for sr in _CANDIDATE_SAMPLE_RATES:
                sr_score = _score_sample_rate(raw_data, bd, ch, bo, sr, file_size, signed)
                if sr_score < _SCORE_THRESHOLD:
                    continue

                combined = bd_score * ch_score * bo_score * sr_score * sign_score
                # Apply common rate prior
                combined *= _COMMON_RATE_PRIOR.get(sr, 1.0)
                # Clamp to [0, 1]
                combined = min(combined, 1.0)

                if combined < _SCORE_THRESHOLD:
                    continue

                fmt = PcmFormat(
                    sample_rate=sr,
                    bit_depth=bd,
                    channels=ch,
                    byte_order=bo,
                    signed=signed,
                )
                preset_name = _match_to_preset(fmt)
                reasons: list[str] = []
                reasons.append(f"bit_depth={bd}({bd_score:.2f})")
                reasons.append(f"ch={ch}({ch_score:.2f})")
                reasons.append(f"byte_order={bo.value}({bo_score:.2f})")
                reasons.append(f"rate={sr}({sr_score:.2f})")
                if bd == 8:
                    sign_label = "signed" if signed else "unsigned"
                    reasons.append(f"sign={sign_label}({sign_score:.2f})")
                reason_str = ", ".join(reasons)

                candidates.append(
                    FormatCandidate(
                        fmt=fmt,
                        confidence=round(combined, 4),
                        preset_name=preset_name,
                        reason=reason_str,
                    )
                )

    # Sort by confidence descending
    candidates.sort(key=lambda c: c.confidence, reverse=True)
    result = candidates[:max_candidates]
    logger.debug(
        "Analysis complete: %d candidates (from %d total)",
        len(result),
        len(candidates),
    )
    for i, c in enumerate(result):
        logger.debug("  #%d confidence=%.4f fmt=%s", i + 1, c.confidence, c.fmt)
    return result


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


def _extract_samples_16(
    data: bytes,
    byte_order: ByteOrder,
) -> list[int]:
    """16-bit PCM 데이터에서 샘플 값을 추출한다.

    Args:
        data: 원시 바이트 데이터.
        byte_order: 바이트 오더.

    Returns:
        부호 있는 16비트 정수 리스트.
    """
    fmt_char = "<h" if byte_order == ByteOrder.LITTLE_ENDIAN else ">h"
    count = len(data) // 2
    samples: list[int] = []
    for i in range(count):
        samples.append(struct.unpack_from(fmt_char, data, i * 2)[0])
    return samples


def _extract_samples_24(
    data: bytes,
    byte_order: ByteOrder,
) -> list[int]:
    """24-bit PCM 데이터에서 샘플 값을 추출한다.

    Args:
        data: 원시 바이트 데이터.
        byte_order: 바이트 오더.

    Returns:
        부호 있는 24비트 정수 리스트.
    """
    count = len(data) // 3
    samples: list[int] = []
    for i in range(count):
        offset = i * 3
        b0, b1, b2 = data[offset], data[offset + 1], data[offset + 2]
        if byte_order == ByteOrder.LITTLE_ENDIAN:
            value = b0 | (b1 << 8) | (b2 << 16)
        else:
            value = (b0 << 16) | (b1 << 8) | b2
        # Sign extend from 24-bit
        if value & 0x800000:
            value -= 0x1000000
        samples.append(value)
    return samples


def _extract_samples_8(data: bytes, signed: bool) -> list[int]:
    """8-bit PCM 데이터에서 샘플 값을 추출한다.

    Args:
        data: 원시 바이트 데이터.
        signed: True이면 부호 있는 8비트, False이면 부호 없는 8비트.

    Returns:
        정수 리스트.
    """
    fmt_char = "b" if signed else "B"
    return [struct.unpack_from(fmt_char, data, i)[0] for i in range(len(data))]


def _compute_stats(samples: list[int]) -> tuple[float, float]:
    """샘플 리스트의 평균과 표준편차를 계산한다.

    Args:
        samples: 정수 샘플 리스트.

    Returns:
        (mean, std_dev) 튜플.
    """
    if not samples:
        return 0.0, 0.0
    n = len(samples)
    mean = sum(samples) / n
    variance = sum((s - mean) ** 2 for s in samples) / n
    return mean, math.sqrt(variance)


def _score_bit_depth(data: bytes, bit_depth: int, file_size: int) -> float:
    """주어진 비트 깊이에 대한 적합도 점수를 계산한다.

    For 8-bit data misinterpreted as 16-bit, the high and low bytes of
    each "sample" are actually independent 8-bit samples — their
    distributions will be similar. This heuristic is used to penalise
    the 16-bit interpretation when the data is likely 8-bit.

    Args:
        data: 분석할 원시 바이트 데이터 (최대 1MB).
        bit_depth: 평가할 비트 깊이 (8, 16, 24).
        file_size: 전체 파일 크기 (바이트).

    Returns:
        0.0 ~ 1.0 사이의 점수.
    """
    sample_width = bit_depth // 8
    if len(data) < sample_width:
        return 0.0

    score = 0.5  # neutral starting point

    # File size divisibility is a strong signal
    if file_size % sample_width == 0:
        score += 0.15
    else:
        score -= 0.2

    if bit_depth == 16:
        samples = _extract_samples_16(data, ByteOrder.LITTLE_ENDIAN)
        if not samples:
            return 0.0
        mean, std = _compute_stats(samples)
        max_val = 32767
        # Mean should be near 0 for typical audio
        if abs(mean) < max_val * 0.1:
            score += 0.15
        elif abs(mean) < max_val * 0.3:
            score += 0.05
        else:
            score -= 0.1
        # Std dev should be reasonable (not too small, not near max)
        if max_val * 0.01 < std < max_val * 0.8:
            score += 0.15
        elif std < max_val * 0.001:
            score -= 0.15  # silence or wrong format
        # Check for excessive clipping
        clip_count = sum(1 for s in samples if abs(s) >= max_val - 1)
        clip_ratio = clip_count / len(samples) if samples else 0
        if clip_ratio > 0.1:
            score -= 0.15

        # Heuristic: detect 8-bit data misinterpreted as 16-bit.
        # True 16-bit audio has smooth sample-to-sample transitions.
        # When 8-bit data is reinterpreted as 16-bit LE, each "sample"
        # combines two independent 8-bit values, producing erratic jumps.
        score = _penalise_rough_16bit(data, score)

    elif bit_depth == 8:
        # Check as unsigned (WAV 8-bit is usually unsigned)
        samples_u = _extract_samples_8(data, signed=False)
        if not samples_u:
            return 0.0
        mean_u, std_u = _compute_stats(samples_u)
        # Unsigned 8-bit audio: mean near 128
        if abs(mean_u - 128) < 30:
            score += 0.15
        elif abs(mean_u - 128) < 50:
            score += 0.05
        # Also check signed interpretation
        samples_s = _extract_samples_8(data, signed=True)
        mean_s, std_s = _compute_stats(samples_s)
        if abs(mean_s) < 30:
            score += 0.05
        # Reasonable std dev for audio
        if 2 < max(std_u, std_s) < 100:
            score += 0.1

        # Positive signal: byte values have moderate mean and spread,
        # consistent with actual 8-bit audio content.
        if 64 <= mean_u <= 192 and 5 < std_u < 100:
            score += 0.10

    elif bit_depth == 24:
        samples = _extract_samples_24(data, ByteOrder.LITTLE_ENDIAN)
        if not samples:
            return 0.0
        mean, std = _compute_stats(samples)
        max_val = 8388607  # 2^23 - 1
        if abs(mean) < max_val * 0.1:
            score += 0.15
        elif abs(mean) < max_val * 0.3:
            score += 0.05
        else:
            score -= 0.1
        if max_val * 0.01 < std < max_val * 0.8:
            score += 0.15
        elif std < max_val * 0.001:
            score -= 0.15
        clip_count = sum(1 for s in samples if abs(s) >= max_val - 1)
        clip_ratio = clip_count / len(samples) if samples else 0
        if clip_ratio > 0.1:
            score -= 0.15

    return max(0.0, min(1.0, score))


def _penalise_rough_16bit(data: bytes, score: float) -> float:
    """8-bit 데이터가 16-bit로 오해석되는 경우를 감지하여 점수를 감점한다.

    True 16-bit audio has smooth sample-to-sample transitions because
    the waveform changes gradually. When 8-bit data is reinterpreted
    as 16-bit LE, each "sample" is built from two independent 8-bit
    values, causing large erratic jumps between consecutive "samples".

    The metric used is *roughness*: average |delta| between consecutive
    samples divided by the peak amplitude. True 16-bit audio typically
    has roughness < 0.20; 8-bit-as-16-bit data typically has roughness
    > 0.40.

    Args:
        data: 원시 바이트 데이터.
        score: 현재 16-bit 점수.

    Returns:
        조정된 점수.
    """
    n_samples = len(data) // 2
    if n_samples < 10:
        return score

    # Use a capped number of samples for performance
    cap = min(n_samples, 10000)
    samples = _extract_samples_16(data[: cap * 2], ByteOrder.LITTLE_ENDIAN)
    if len(samples) < 2:
        return score

    peak = max(abs(s) for s in samples)
    if peak == 0:
        return score

    total_delta = sum(abs(samples[i + 1] - samples[i]) for i in range(len(samples) - 1))
    roughness = (total_delta / (len(samples) - 1)) / peak

    if roughness > 0.40:
        # Very rough — strong evidence this is not true 16-bit audio
        score -= 0.30
    elif roughness > 0.25:
        score -= 0.15

    return score


def _score_channels(
    data: bytes,
    bit_depth: int,
    channels: int,
    file_size: int,
) -> float:
    """채널 수에 대한 적합도 점수를 계산한다.

    Mono is favoured as the default interpretation. Stereo scores high
    only when L/R correlation is moderate (0.3-0.95), which indicates
    two genuinely related but distinct channels. Very high correlation
    (>0.95) suggests mono data misinterpreted as stereo (adjacent
    samples of a smooth signal), so it is penalised.

    Args:
        data: 원시 바이트 데이터.
        bit_depth: 비트 깊이.
        channels: 평가할 채널 수 (1 또는 2).
        file_size: 전체 파일 크기.

    Returns:
        0.0 ~ 1.0 사이의 점수.
    """
    sample_width = bit_depth // 8
    frame_size = sample_width * channels

    if channels == 1:
        # Mono is the default/favoured interpretation.
        score = 0.70
        if file_size % frame_size != 0:
            score -= 0.15
        return max(0.0, min(1.0, score))

    # --- Stereo (channels == 2) ---
    score = 0.40  # start lower than mono baseline

    # File size alignment with frame size
    if file_size % frame_size == 0:
        score += 0.05
    else:
        score -= 0.15

    # For very small files, stereo is unlikely
    min_stereo_bytes = sample_width * 2 * 100  # at least 100 frames
    if file_size < min_stereo_bytes:
        score -= 0.1

    # L/R correlation and identity analysis
    lr_stats = _compute_lr_stats(data, bit_depth)
    if lr_stats is not None:
        corr, norm_mad = lr_stats
        if corr > 0.95 and norm_mad < 0.01:
            # Very high correlation AND nearly identical L/R values:
            # genuine stereo with identical (or near-identical) channels.
            score += 0.30
        elif corr > 0.95:
            # High correlation but L/R values differ meaningfully:
            # mono data misinterpreted as stereo (adjacent samples of
            # a smooth waveform are correlated but not identical).
            score -= 0.15
        elif 0.5 <= corr <= 0.95:
            # Moderate-to-high correlation: plausible stereo content
            score += 0.25
        elif 0.3 <= corr < 0.5:
            score += 0.10
        else:
            # Very low correlation (<0.3): unlikely to be stereo
            score -= 0.05

    return max(0.0, min(1.0, score))


def _compute_lr_stats(
    data: bytes,
    bit_depth: int,
) -> tuple[float, float] | None:
    """L/R 상관계수와 정규화된 평균 절대 차이를 계산한다.

    데이터를 스테레오로 해석한 뒤 좌/우 채널 간 피어슨 상관계수와
    정규화된 MAD (mean absolute difference / peak)를 반환한다.
    이를 통해 '진정한 스테레오 (L≈R)'와 '모노를 스테레오로 오해석'을
    구분할 수 있다.

    Args:
        data: 원시 바이트 데이터.
        bit_depth: 비트 깊이 (8, 16, 24).

    Returns:
        (correlation, normalized_mad) 튜플 또는 계산 불가 시 None.
    """
    if bit_depth == 16:
        samples = _extract_samples_16(data, ByteOrder.LITTLE_ENDIAN)
    elif bit_depth == 8:
        samples = _extract_samples_8(data, signed=False)
    elif bit_depth == 24:
        samples = _extract_samples_24(data, ByteOrder.LITTLE_ENDIAN)
    else:
        return None

    if len(samples) < 4:
        return None

    left = samples[0::2]
    right = samples[1::2]
    n = min(len(left), len(right))
    if n == 0:
        return None

    corr = _pearson_correlation(left[:n], right[:n])

    # Normalized MAD: average |L[i] - R[i]| / peak amplitude
    peak = max(abs(s) for s in samples)
    if peak == 0:
        norm_mad = 0.0
    else:
        mad = sum(abs(left[i] - right[i]) for i in range(n)) / n
        norm_mad = mad / peak

    return corr, norm_mad


def _pearson_correlation(xs: list[int], ys: list[int]) -> float:
    """두 정수 리스트의 피어슨 상관계수를 계산한다.

    Args:
        xs: 첫 번째 샘플 리스트.
        ys: 두 번째 샘플 리스트.

    Returns:
        -1.0 ~ 1.0 사이의 상관계수. 계산 불가 시 0.0.
    """
    n = len(xs)
    if n == 0:
        return 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    denom = math.sqrt(var_x * var_y)
    if denom < 1e-12:
        return 0.0
    return cov / denom


def _score_byte_order(
    data: bytes,
    bit_depth: int,
    byte_order: ByteOrder,
) -> float:
    """바이트 오더에 대한 적합도 점수를 계산한다.

    Args:
        data: 원시 바이트 데이터.
        bit_depth: 비트 깊이 (16 또는 24).
        byte_order: 평가할 바이트 오더.

    Returns:
        0.0 ~ 1.0 사이의 점수.
    """
    if bit_depth == 8:
        return 1.0

    if bit_depth == 16:
        samples = _extract_samples_16(data, byte_order)
    elif bit_depth == 24:
        samples = _extract_samples_24(data, byte_order)
    else:
        return 0.0

    if not samples:
        return 0.0

    max_val = (1 << (bit_depth - 1)) - 1
    mean, std = _compute_stats(samples)

    score = 0.5

    # Wrong endianness tends to produce values clustered near extremes
    # or with abnormal mean
    if abs(mean) < max_val * 0.15:
        score += 0.2
    elif abs(mean) < max_val * 0.3:
        score += 0.1
    else:
        score -= 0.2

    # Reasonable std dev
    if max_val * 0.005 < std < max_val * 0.8:
        score += 0.15
    elif std < max_val * 0.001:
        score -= 0.1

    # Check for values near extremes (wrong endianness signal)
    extreme_count = sum(1 for s in samples if abs(s) > max_val * 0.95)
    extreme_ratio = extreme_count / len(samples) if samples else 0
    if extreme_ratio > 0.3:
        score -= 0.2
    elif extreme_ratio < 0.05:
        score += 0.1

    return max(0.0, min(1.0, score))


def _score_sample_rate(
    data: bytes,
    bit_depth: int,
    channels: int,
    byte_order: ByteOrder,
    sample_rate: int,
    file_size: int,
    signed: bool,
) -> float:
    """샘플레이트에 대한 적합도 점수를 계산한다.

    Args:
        data: 원시 바이트 데이터.
        bit_depth: 비트 깊이.
        channels: 채널 수.
        byte_order: 바이트 오더.
        sample_rate: 평가할 샘플레이트.
        file_size: 전체 파일 크기.
        signed: 부호 여부.

    Returns:
        0.0 ~ 1.0 사이의 점수.
    """
    sample_width = bit_depth // 8
    frame_size = sample_width * channels
    total_frames = file_size / frame_size if frame_size > 0 else 0
    implied_duration = total_frames / sample_rate if sample_rate > 0 else 0

    score = 0.5

    # Implied duration should be reasonable (0.1s ~ 3600s)
    if 0.1 <= implied_duration <= 3600:
        score += 0.15
    elif implied_duration < 0.01 or implied_duration > 36000:
        score -= 0.2
    else:
        score += 0.05

    # Zero-crossing rate analysis
    if bit_depth == 16:
        samples = _extract_samples_16(data, byte_order)
    elif bit_depth == 24:
        samples = _extract_samples_24(data, byte_order)
    elif bit_depth == 8:
        samples = _extract_samples_8(data, signed)
        if not signed:
            # Center around 0 for zero-crossing analysis
            samples = [s - 128 for s in samples]
    else:
        return max(0.0, min(1.0, score))

    # Extract mono signal for zero-crossing analysis
    mono_samples = samples[0::2] if channels == 2 and len(samples) >= 2 else samples

    if len(mono_samples) > 1:
        analysis_frames = len(mono_samples)
        analysis_duration = analysis_frames / sample_rate if sample_rate > 0 else 0

        if analysis_duration > 0:
            zero_crossings = _count_zero_crossings(mono_samples)
            zcr = zero_crossings / analysis_duration

            # Typical ranges:
            # Speech: ~100-300 crossings/sec → favors lower rates
            # Music: ~1000-5000 crossings/sec → favors higher rates
            if zcr < 500:
                # Likely speech-like content
                if sample_rate <= 16000:
                    score += 0.1
                elif sample_rate <= 22050:
                    score += 0.05
            elif zcr < 3000:
                # Moderate → medium rates
                if 16000 <= sample_rate <= 48000:
                    score += 0.1
            else:
                # High frequency content → higher rates
                if sample_rate >= 44100:
                    score += 0.1
                elif sample_rate >= 22050:
                    score += 0.05

    return max(0.0, min(1.0, score))


def _count_zero_crossings(samples: list[int]) -> int:
    """샘플 배열에서 영점 교차 횟수를 센다.

    Args:
        samples: 정수 샘플 리스트.

    Returns:
        부호가 바뀌는 횟수.
    """
    if len(samples) < 2:
        return 0
    crossings = 0
    prev_positive = samples[0] >= 0
    for s in samples[1:]:
        curr_positive = s >= 0
        if curr_positive != prev_positive:
            crossings += 1
            prev_positive = curr_positive
    return crossings


def _score_signedness(data: bytes, bit_depth: int, signed: bool) -> float:
    """부호 여부에 대한 적합도 점수를 계산한다.

    16/24비트는 WAV 표준에 따라 항상 signed이므로 점수 1.0.
    8비트의 경우 데이터 분포로 판단한다.

    Args:
        data: 원시 바이트 데이터.
        bit_depth: 비트 깊이.
        signed: 평가할 부호 여부.

    Returns:
        0.0 ~ 1.0 사이의 점수.
    """
    if bit_depth > 8:
        # 16/24-bit are always signed per WAV spec
        return 1.0 if signed else 0.0

    # 8-bit analysis
    samples = _extract_samples_8(data, signed=False)  # always read as unsigned first
    if not samples:
        return 0.5

    mean, _ = _compute_stats(samples)

    if signed:
        # If mean is near 0 when interpreted as signed, it's signed
        # Signed 8-bit: values 0-127 positive, 128-255 negative (-128 to -1)
        if abs(mean - 128) < 20:
            # Mean near 128 as unsigned → near 0 as signed → could be either
            return 0.5
        elif mean < 100:
            # Mean well below 128 → probably signed (centered near 0)
            return 0.6
        else:
            return 0.4
    else:
        # Unsigned: mean should be near 128 for typical audio
        if abs(mean - 128) < 20:
            return 0.7
        elif abs(mean - 128) < 50:
            return 0.5
        else:
            return 0.3


def _match_to_preset(fmt: PcmFormat) -> str | None:
    """PcmFormat이 알려진 프리셋과 일치하는지 확인한다.

    Args:
        fmt: 비교할 PcmFormat.

    Returns:
        매칭되는 프리셋 이름. 없으면 None.
    """
    for name, preset_fmt in PRESETS.items():
        if preset_fmt is None:
            continue
        if (
            fmt.sample_rate == preset_fmt.sample_rate
            and fmt.bit_depth == preset_fmt.bit_depth
            and fmt.channels == preset_fmt.channels
            and fmt.byte_order == preset_fmt.byte_order
            and fmt.signed == preset_fmt.signed
        ):
            return name
    return None
