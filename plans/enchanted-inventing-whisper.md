# PCM to WAV Converter - 개발 계획서

## 1. 프로젝트 개요

### 1.1 목적

PCM(Raw Audio) 파일을 WAV 파일로 변환하는 GUI 데스크탑 도구를 개발한다.
PCM 파일은 헤더가 없는 원시 오디오 데이터이므로, 사용자가 샘플레이트/비트깊이/채널 등 파라미터를 지정하면 올바른 WAV 헤더를 붙여 변환한다.

### 1.2 주요 기능

- Tkinter 기반 GUI (Windows 11 네이티브 룩)
- 배치 변환 (여러 파일 동시 처리, 진행률 표시, 취소 기능)
- 프리셋 지원 (CD Quality, Telephony, DVD 등)
- 커스텀 파라미터 입력 (샘플레이트, 비트깊이, 채널, 바이트 오더, 부호)
- 외부 라이브러리 없이 Python 표준 라이브러리만 사용

### 1.3 기술 스택

- Python 3.10+
- 표준 라이브러리: `wave`, `struct`, `array`, `enum`, `tkinter`, `threading`, `queue`, `dataclasses`, `pathlib`, `json`, `logging`, `ctypes`, `time`, `sys`
- 외부 의존성: 없음

### 1.4 버전 정보

- 패키지 버전: `0.1.0`
- 버전 관리: SemVer (MAJOR.MINOR.PATCH)
- `pcm2wav/__init__.py`에 `__version__ = "0.1.0"` 정의

---

## 2. 프로젝트 구조

```
PCM2WAV/
├── pcm2wav/
│   ├── __init__.py          # 패키지 초기화, __version__
│   ├── models.py            # 데이터 타입 (PcmFormat, ByteOrder, ConversionResult, PcmConversionError)
│   ├── converter.py         # 핵심 변환 로직 (PCM→WAV)
│   ├── presets.py           # 프리셋 정의 (CD, 전화, DVD 등)
│   ├── app.py               # Tkinter GUI 메인 앱
│   └── widgets.py           # 커스텀 위젯 (ParameterPanel, FileListPanel)
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # 테스트 픽스처 (known-pattern PCM 파일 생성)
│   ├── test_models.py       # PcmFormat 유효성 테스트
│   ├── test_converter.py    # 변환 로직 단위 테스트
│   └── test_presets.py      # 프리셋 검증 테스트
├── docs/
│   └── runbooks/
│       └── weekly/          # 작업일지
├── main.py                  # 실행 진입점
└── pyproject.toml           # 프로젝트 설정 (ruff, mypy, pytest)
```

의존 방향: `app.py` → `widgets.py` → `models.py` ← `converter.py`, `models.py` ← `presets.py`

`PcmFormat` 등 데이터 타입을 `models.py`로 분리하여 `widgets.py`가 `converter.py`에 직접 의존하지 않도록 한다.

---

## 3. 핵심 모듈 설계

### 3.1 `models.py` - 데이터 타입

```python
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ByteOrder(Enum):
    LITTLE_ENDIAN = "little"
    BIG_ENDIAN = "big"


class PcmConversionError(Exception):
    """변환 실패 커스텀 예외."""


VALID_BIT_DEPTHS = frozenset({8, 16, 24})
MIN_SAMPLE_RATE = 1
MAX_SAMPLE_RATE = 384_000
VALID_CHANNELS = frozenset({1, 2})


@dataclass(frozen=True)
class PcmFormat:
    """PCM 포맷 파라미터.

    Attributes:
        sample_rate: 샘플레이트 (Hz). 1~384,000 범위.
        bit_depth: 비트 깊이. 8, 16, 24만 허용 (v1).
        channels: 채널 수. 1(mono) 또는 2(stereo).
        byte_order: 바이트 오더. 8-bit에서는 무시됨.
        signed: 8-bit 부호 여부. bit_depth > 8이면 반드시 True.
    """
    sample_rate: int = 44100
    bit_depth: int = 16
    channels: int = 1
    byte_order: ByteOrder = ByteOrder.LITTLE_ENDIAN
    signed: bool = True

    def __post_init__(self) -> None:
        if self.bit_depth not in VALID_BIT_DEPTHS:
            raise ValueError(
                f"bit_depth must be one of {sorted(VALID_BIT_DEPTHS)}, "
                f"got {self.bit_depth}"
            )
        if not (MIN_SAMPLE_RATE <= self.sample_rate <= MAX_SAMPLE_RATE):
            raise ValueError(
                f"sample_rate must be {MIN_SAMPLE_RATE}~{MAX_SAMPLE_RATE}, "
                f"got {self.sample_rate}"
            )
        if self.channels not in VALID_CHANNELS:
            raise ValueError(
                f"channels must be one of {sorted(VALID_CHANNELS)}, "
                f"got {self.channels}"
            )
        if self.bit_depth > 8 and not self.signed:
            raise ValueError(
                "WAV standard requires 16/24-bit PCM to be signed. "
                "unsigned is only valid for 8-bit."
            )

    @property
    def sample_width(self) -> int:
        """Bytes per sample per channel."""
        return self.bit_depth // 8

    @property
    def frame_size(self) -> int:
        """Bytes per frame (all channels)."""
        return self.sample_width * self.channels


@dataclass
class ConversionResult:
    """단일 파일 변환 결과 (mutable — 변환 과정에서 필드가 채워짐).

    Attributes:
        input_path: 입력 PCM 파일 경로.
        output_path: 출력 WAV 파일 경로 (실패 시 None).
        success: 변환 성공 여부.
        error_message: 실패 시 오류 메시지 (성공 시 None).
        elapsed_seconds: 변환 소요 시간 (초).
        frames_written: 기록된 오디오 프레임 수.
        output_size_bytes: 출력 파일 크기 (바이트).
    """
    input_path: Path
    output_path: Path | None
    success: bool
    error_message: str | None = None
    elapsed_seconds: float = 0.0
    frames_written: int = 0
    output_size_bytes: int = 0
```

v1에서 32-bit PCM은 지원하지 않는다. Python `wave` 모듈이 `sampwidth=4`에서 `WAVEFORMATEXTENSIBLE` 없이 기본 `fmt` 청크만 작성하므로, 다수 디코더가 거부한다. v2에서 수동 헤더 작성으로 지원 예정.

---

### 3.2 `converter.py` - 변환 엔진

가장 중요한 모듈. GUI와 완전히 독립적으로 동작.

#### 핵심 함수

| 함수 | 설명 |
|------|------|
| `convert_pcm_to_wav()` | 단일 파일 변환 (청크 단위, progress callback) |
| `batch_convert()` | 다수 파일 변환 (progress callback, cancel event) |
| `validate_pcm_file()` | 파일 존재/크기/프레임 정렬/4GB 한계 사전 검증 |
| `swap_byte_order()` | 바이트 오더 변환 (little-endian으로) |
| `convert_8bit_signedness()` | 8-bit signed→unsigned 변환 (XOR 0x80) |

#### 변환 파이프라인 (`convert_pcm_to_wav`) 상세 명세

```python
import logging
import threading
import time
import wave
from pathlib import Path
from typing import Callable

from pcm2wav.models import ByteOrder, ConversionResult, PcmConversionError, PcmFormat

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int], None]  # (bytes_processed, total_bytes)

def convert_pcm_to_wav(
    pcm_path: Path,
    wav_path: Path,
    fmt: PcmFormat,
    progress_callback: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> ConversionResult:
    """단일 PCM 파일을 WAV로 변환.

    변환 파이프라인:
    1. 입력 파일 존재/읽기 권한 검증
    2. validate_pcm_file()로 사전 검증 (hard error 시 즉시 실패)
    3. wave.open()으로 출력 파일 생성
    4. WAV 파라미터 설정 (setnchannels, setsampwidth, setframerate, setnframes(0))
    5. 청크 루프:
       a. 프레임 정렬된 청크 크기로 입력 파일 읽기
       b. byte_order가 BIG_ENDIAN이면 swap_byte_order() 적용
       c. bit_depth==8이고 signed==True이면 convert_8bit_signedness() 적용
       d. wave.writeframes(chunk) — nframes는 자동 누적
       e. cancel_event 확인 → 설정 시 부분 파일 삭제 후 종료
       f. progress_callback 호출
    6. wave 파일 close
    7. ConversionResult 반환

    에러 처리:
    - FileNotFoundError → PcmConversionError("입력 파일을 찾을 수 없습니다")
    - PermissionError → PcmConversionError("파일 접근 권한이 없습니다")
    - OSError (disk full 등) → PcmConversionError("파일 쓰기 오류")
    - 변환 실패 시 부분 출력 파일 삭제
    - wave.open() 실패 시 PcmConversionError로 래핑
    """
    start_time = time.monotonic()
    try:
        # 1. 입력 파일 검증
        if not pcm_path.exists():
            raise PcmConversionError(f"입력 파일을 찾을 수 없습니다: {pcm_path}")
        if not pcm_path.is_file():
            raise PcmConversionError(f"파일이 아닙니다: {pcm_path}")

        file_size = pcm_path.stat().st_size
        if file_size == 0:
            raise PcmConversionError(f"빈 파일입니다: {pcm_path}")

        # 2. 사전 검증
        errors, warnings = validate_pcm_file(pcm_path, fmt)
        if errors:
            raise PcmConversionError("; ".join(errors))
        for w in warnings:
            logger.warning(w)

        # 3-4. WAV 출력 파일 생성 + 파라미터 설정
        needs_swap = (fmt.byte_order == ByteOrder.BIG_ENDIAN and fmt.sample_width > 1)
        needs_sign_convert = (fmt.bit_depth == 8 and fmt.signed)
        chunk_size = _aligned_chunk_size(fmt.frame_size)

        with open(pcm_path, "rb") as pcm_file:
            with wave.open(str(wav_path), "wb") as wav_file:
                wav_file.setnchannels(fmt.channels)
                wav_file.setsampwidth(fmt.sample_width)
                wav_file.setframerate(fmt.sample_rate)
                wav_file.setnframes(0)  # writeframes()가 자동 누적

                # 5. 청크 루프
                bytes_processed = 0
                while True:
                    if cancel_event and cancel_event.is_set():
                        break

                    chunk = pcm_file.read(chunk_size)
                    if not chunk:
                        break

                    if needs_swap:
                        chunk = swap_byte_order(chunk, fmt.sample_width)

                    if needs_sign_convert:
                        chunk = convert_8bit_signedness(chunk)

                    wav_file.writeframes(chunk)

                    bytes_processed += len(chunk)
                    if progress_callback:
                        progress_callback(bytes_processed, file_size)

        # 취소 시 부분 파일 삭제
        if cancel_event and cancel_event.is_set():
            _safe_delete(wav_path)
            elapsed = time.monotonic() - start_time
            return ConversionResult(
                input_path=pcm_path, output_path=None,
                success=False, error_message="사용자에 의해 취소됨",
                elapsed_seconds=elapsed,
            )

        # 성공 결과
        elapsed = time.monotonic() - start_time
        output_size = wav_path.stat().st_size
        frames = file_size // fmt.frame_size
        return ConversionResult(
            input_path=pcm_path, output_path=wav_path,
            success=True, elapsed_seconds=elapsed,
            frames_written=frames, output_size_bytes=output_size,
        )

    except PcmConversionError:
        _safe_delete(wav_path)
        raise
    except Exception as exc:
        _safe_delete(wav_path)
        raise PcmConversionError(f"변환 오류: {exc}") from exc


def _safe_delete(path: Path) -> None:
    """파일이 존재하면 삭제. 실패해도 예외 무시."""
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass
```

#### 청크 처리 (프레임 정렬)

```python
CHUNK_SIZE = 262_144  # 256KB

def _aligned_chunk_size(frame_size: int) -> int:
    """프레임 경계에 정렬된 청크 크기 계산."""
    return max(frame_size, (CHUNK_SIZE // frame_size) * frame_size)
```

#### 바이트 스왑 전략

```python
import array

def swap_byte_order(data: bytes, sample_width: int) -> bytes:
    """PCM 데이터의 바이트 오더를 스왑하여 little-endian으로 변환.

    Args:
        data: PCM 바이트 데이터 (길이는 sample_width의 배수여야 함).
        sample_width: 샘플당 바이트 수 (1, 2, 3).

    Returns:
        little-endian으로 변환된 바이트 데이터.

    Note:
        - 8-bit (sample_width=1): no-op (1바이트, 엔디언 없음).
        - 16-bit (sample_width=2): array.array('H').byteswap() 사용 (고성능).
        - 24-bit (sample_width=3): bytearray 슬라이스 스왑.
          Python은 RHS 튜플 전체를 평가한 뒤 LHS에 대입하므로 안전함.
    """
    if sample_width == 1:
        return data

    if sample_width == 2:
        arr = array.array("H", data)
        arr.byteswap()
        return arr.tobytes()

    if sample_width == 3:
        ba = bytearray(data)
        ba[0::3], ba[2::3] = ba[2::3], ba[0::3]
        return bytes(ba)

    raise PcmConversionError(f"지원하지 않는 sample_width: {sample_width}")
```

#### 8-bit 부호 변환

```python
_SIGNEDNESS_TABLE = bytes(range(256))[128:] + bytes(range(256))[:128]

def convert_8bit_signedness(data: bytes) -> bytes:
    """8-bit signed PCM → unsigned PCM (WAV 표준) 변환.

    bytes.translate()로 O(n) 최적화.
    """
    return data.translate(_SIGNEDNESS_TABLE)
```

#### 파일 사전 검증

```python
def validate_pcm_file(
    pcm_path: Path, fmt: PcmFormat
) -> tuple[list[str], list[str]]:
    """PCM 파일 사전 검증.

    Returns:
        (errors, warnings) 튜플.
        - errors: 변환을 차단하는 심각한 문제 (빈 리스트 = 진행 가능).
        - warnings: 주의사항 (변환은 진행하되 사용자에게 알림).
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not pcm_path.exists():
        errors.append(f"파일을 찾을 수 없습니다: {pcm_path}")
        return errors, warnings

    file_size = pcm_path.stat().st_size

    if file_size == 0:
        errors.append("빈 파일입니다 (0 바이트)")
        return errors, warnings

    # 4GB 한계 검증
    # WAV 구조: RIFF header(12) + fmt chunk(24) + data chunk header(8) + data = 44 + data
    # RIFF size field = total_file_size - 8, data subchunk size field = file_size
    # 두 필드 모두 uint32 (최대 0xFFFFFFFF)
    max_uint32 = 0xFFFF_FFFF
    pad_byte = file_size % 2  # RIFF spec: 홀수 크기 data 청크 뒤에 1바이트 패딩
    riff_payload = file_size + 36 + pad_byte  # "WAVE"(4) + fmt chunk(24) + data header(8) + data + pad

    if file_size > max_uint32:
        errors.append(
            f"PCM 데이터 크기({file_size:,}B)가 WAV data 청크 한계(4GB)를 초과합니다"
        )
    elif riff_payload > max_uint32:
        errors.append(
            f"출력 WAV RIFF 페이로드({riff_payload:,}B)가 4GB를 초과합니다"
        )

    # 프레임 정렬 검증
    if file_size % fmt.frame_size != 0:
        remainder = file_size % fmt.frame_size
        truncated_frames = file_size // fmt.frame_size
        warnings.append(
            f"파일 크기({file_size:,}B)가 프레임 크기({fmt.frame_size}B)의 배수가 아닙니다. "
            f"마지막 {remainder}B는 잘림 처리됩니다 (총 {truncated_frames}프레임 변환)."
        )

    return errors, warnings
```

#### 배치 변환

```python
def batch_convert(
    files: list[tuple[Path, Path]],  # (input_pcm, output_wav) 쌍
    fmt: PcmFormat,
    progress_callback: Callable[[int, int, int, int], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> list[ConversionResult]:
    """다수 파일 배치 변환.

    Args:
        files: (입력 PCM 경로, 출력 WAV 경로) 튜플 리스트.
        fmt: PCM 포맷 파라미터.
        progress_callback: (file_index, total_files, bytes_processed, file_total_bytes) 콜백.
        cancel_event: 취소 이벤트. 설정 시 현재 파일 변환 후 중단.

    Returns:
        ConversionResult 리스트. 실패한 파일도 포함 (success=False).

    동작:
        - 단일 파일 실패 시 로그 기록 후 다음 파일 계속 진행.
        - cancel_event 설정 시 현재 파일 완료 후 나머지 파일은 건너뜀.
        - 취소된 파일의 부분 출력은 삭제됨 (convert_pcm_to_wav 내부 처리).
    """
```

---

### 3.3 `presets.py` - 포맷 프리셋

순수 데이터 모듈. GUI 드롭다운에서 사용. dict 삽입 순서가 GUI 표시 순서를 결정 (Python 3.7+ 보장).

모든 프리셋은 little-endian, signed를 기본값으로 사용. big-endian/unsigned가 필요하면 "Custom" 선택 후 수동 설정.

```python
from pcm2wav.models import ByteOrder, PcmFormat

PRESETS: dict[str, PcmFormat | None] = {
    "CD Quality (44100Hz, 16-bit, Stereo)":       PcmFormat(44100, 16, 2),
    "CD Quality Mono (44100Hz, 16-bit, Mono)":    PcmFormat(44100, 16, 1),
    "DVD Quality (48000Hz, 24-bit, Stereo)":      PcmFormat(48000, 24, 2),
    "Telephony (8000Hz, 16-bit, Mono)":           PcmFormat(8000, 16, 1),
    "Wideband Telephony (16000Hz, 16-bit, Mono)": PcmFormat(16000, 16, 1),
    "Voice Recording (22050Hz, 16-bit, Mono)":    PcmFormat(22050, 16, 1),
    "DAT Quality (48000Hz, 16-bit, Stereo)":      PcmFormat(48000, 16, 2),
    "Custom": None,  # GUI에서 수동 입력 활성화 신호
}
DEFAULT_PRESET_NAME = "CD Quality Mono (44100Hz, 16-bit, Mono)"
```

---

### 3.4 `widgets.py` - 커스텀 GUI 위젯

#### ParameterPanel (ttk.LabelFrame)

- 프리셋 드롭다운 (Combobox, read-only)
- 샘플레이트 입력 (Combobox: 8000, 11025, 16000, 22050, 44100, 48000, 96000) — 직접 입력 가능, 검증 적용
- 비트깊이 선택 (Combobox: 8, 16, 24, read-only)
- 채널 선택 (Combobox: Mono, Stereo, read-only)
- 바이트 오더 선택 (Combobox: Little-Endian, Big-Endian, read-only)
- 부호 선택 (Combobox: Signed, Unsigned) — 8-bit 선택 시에만 활성화, 그 외 비활성화+Signed 고정
- 프리셋 선택 시 필드 자동입력 + 비활성화 / "Custom" 선택 시 활성화

```python
class ParameterPanel(ttk.LabelFrame):
    def get_format(self) -> PcmFormat:
        """현재 UI 값으로 PcmFormat 생성. 유효하지 않으면 ValueError 발생."""
        ...

    def set_format(self, fmt: PcmFormat) -> None:
        """주어진 PcmFormat으로 UI 필드 갱신."""
        ...

    def set_enabled(self, enabled: bool) -> None:
        """변환 중 전체 패널 비활성화/활성화."""
        ...
```

#### FileListPanel (ttk.LabelFrame)

- Treeview: 파일명, 크기, 상태 표시
  - 컬럼 너비: 파일명(확장 가능, min 200px), 크기(100px, 고정), 상태(150px, 고정)
  - 컬럼 리사이즈 가능
- 버튼: [파일 추가] [폴더 추가] [선택 제거] [전체 삭제]
- 파일 필터: `.pcm`, `.raw`, `.bin`, `.dat`, `.snd`, 모든 파일(*.*)
- 중복 파일 처리: 같은 절대 경로의 파일을 다시 추가하면 무시
- 폴더 추가 동작: 비재귀 (1단계 파일만), 필터 확장자만 포함, 파일 없으면 알림
- 파일 크기 표시: < 1KB → "N B", < 1MB → "N.N KB", < 1GB → "N.N MB", else → "N.N GB" (1KB=1024B)

```python
class FileListPanel(ttk.LabelFrame):
    def add_files(self, paths: list[Path]) -> int:
        """파일 추가. 중복 제외. 추가된 파일 수 반환."""
        ...

    def get_files(self) -> list[Path]:
        """현재 파일 목록 반환."""
        ...

    def update_status(self, path: Path, status: str) -> None:
        """특정 파일의 상태 컬럼 갱신."""
        ...

    def clear(self) -> None:
        """전체 파일 목록 삭제."""
        ...

    def is_empty(self) -> bool:
        """파일 목록이 비어있는지 확인."""
        ...

    def set_enabled(self, enabled: bool) -> None:
        """변환 중 버튼 비활성화/활성화."""
        ...
```

---

### 3.5 `app.py` - 메인 GUI 앱

#### GUI 상태 머신

```
IDLE ──[변환 시작]──→ CONVERTING ──[완료]──→ COMPLETED ──[자동]──→ IDLE
  │                      │                       │
  │                      └──[취소]──→ CANCELLED ──┘
  │                      │
  │                      └──[전체 오류]──→ ERROR ──[자동]──→ IDLE
  └──────────────────────────────────────────────────────────────────
```

| 상태 | ParameterPanel | FileListPanel 버튼 | 변환 시작 | 취소 | 프로그래스바 |
|------|----------------|-------------------|----------|------|-------------|
| IDLE | 활성화 | 활성화 | 활성화 (파일 있을 때) | 비활성화 | 숨김/0% |
| CONVERTING | 비활성화 | 비활성화 | 비활성화 | 활성화 | 표시/갱신 |
| COMPLETED | 활성화 | 활성화 | 활성화 | 비활성화 | 100% 유지 (2초 후 리셋) |
| CANCELLED | 활성화 | 활성화 | 활성화 | 비활성화 | 현재값 유지 (2초 후 리셋) |
| ERROR | 활성화 | 활성화 | 활성화 | 비활성화 | 숨김/0% |

#### 스레드 안전 아키텍처

```python
class Pcm2WavApp:
    def __init__(self):
        self.root = tk.Tk()
        self.msg_queue: queue.Queue[tuple] = queue.Queue()
        self._cancel_event = threading.Event()
        self._convert_thread_ref: threading.Thread | None = None
        self.root.after(100, self._poll_queue)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        """윈도우 닫기 핸들러. 변환 중이면 확인 다이얼로그 표시."""
        if self._convert_thread_ref and self._convert_thread_ref.is_alive():
            if not messagebox.askokcancel("종료 확인", "변환이 진행 중입니다. 종료하시겠습니까?"):
                return
            self._cancel_event.set()
            self._convert_thread_ref.join(timeout=5.0)
        self.root.destroy()

    def _start_conversion(self):
        """변환 시작. cancel_event를 반드시 clear한 후 스레드 시작."""
        self._cancel_event.clear()
        self._convert_thread_ref = threading.Thread(
            target=self._convert_thread, daemon=True, ...
        )
        self._convert_thread_ref.start()

    def _poll_queue(self):
        """메인 스레드에서 큐를 폴링하여 GUI 업데이트."""
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                self._handle_message(msg)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)
```

#### 메시지 큐 프로토콜

```python
MessageType = Literal[
    "file_progress",   # (file_index, total_files, bytes_done, bytes_total)
    "file_complete",   # (file_index, ConversionResult)
    "batch_complete",  # (list[ConversionResult],)
    "error",           # (error_message,)
]
```

#### 진행률 표시 모델

- **배치 진행률** (파일 수 기준): 상태 라벨에 "변환 중: filename.pcm (2/5 파일)" 표시.
- **파일 진행률** (바이트 기준): `ttk.Progressbar` (determinate mode, maximum=100).
  - `progress_percent = bytes_processed / file_total_bytes * 100`
- 각 파일 완료 시 Treeview의 상태 컬럼 갱신 ("변환완료 ✓" 또는 "오류: {message}").

#### 출력 설정 상호작용

- **"입력 파일과 같은 폴더에 저장" 체크박스**:
  - 체크 시: 출력 폴더 필드 + 찾아보기 버튼 비활성화. 각 파일의 출력은 입력 파일과 동일 디렉토리.
  - 해제 시: 출력 폴더 필드 + 찾아보기 버튼 활성화. 모든 출력이 지정 폴더로.
- **중복 시 처리 옵션** (Radiobutton):
  - 덮어쓰기: 기존 파일 삭제 후 재생성.
  - 건너뛰기: ConversionResult에 `success=False, error_message="파일 이미 존재"` 기록.
  - 번호 추가: `output.wav` → `output_1.wav` → `output_2.wav` → ...
- **출력 파일명 규칙**:
  - `.pcm`, `.raw`, `.bin`, `.dat`, `.snd` 확장자 → `.wav`로 교체.
  - 확장자 없음 → `.wav` 추가.
  - 다중 점(`.`) 포함: 마지막 확장자만 교체 (예: `file.backup.pcm` → `file.backup.wav`).
  - 출력 파일이 다른 프로세스에 잠겨 있으면 `PermissionError` → "파일이 사용 중입니다" 에러.

#### 키보드 단축키

| 단축키 | 동작 |
|--------|------|
| `Ctrl+O` | 파일 추가 다이얼로그 열기 |
| `Ctrl+Shift+O` | 폴더 추가 다이얼로그 열기 |
| `Delete` | 선택 파일 제거 |
| `Enter` / `Ctrl+Enter` | 변환 시작 (IDLE 상태에서만) |
| `Escape` | 변환 취소 (CONVERTING 상태에서만) |

---

## 4. GUI 레이아웃

```
+---------------------------------------------------------------+
|  PCM to WAV Converter v0.1.0                        [_][O][X] |
+---------------------------------------------------------------+
|  +-- 포맷 설정 --------------------------------------------+  |
|  |  프리셋: [CD Quality Mono (44100, 16-bit, Mono)      v]  |  |
|  |  샘플레이트: [44100 v]    비트깊이: [16 v]              |  |
|  |  채널:       [Mono  v]    바이트 오더: [Little-Endian v] |  |
|  |  부호:       [Signed v]   ← 8-bit 선택 시에만 활성화    |  |
|  +----------------------------------------------------------+  |
|                                                                |
|  +-- 입력 파일 --------------------------------------------+  |
|  |  [파일 추가]  [폴더 추가]  [선택 제거]  [전체 삭제]      |  |
|  |  +------------------------------------------------------+  |
|  |  | 파일명            | 크기     | 상태                 |  |  |
|  |  |-------------------+---------+----------------------|  |  |
|  |  | recording_01.pcm  | 1.2 MB  | 준비                 |  |  |
|  |  | recording_02.raw  | 843 KB  | 변환완료 ✓           |  |  |
|  |  | recording_03.bin  | 0 B     | 오류: 빈 파일         |  |  |
|  |  +------------------------------------------------------+  |
|  +----------------------------------------------------------+  |
|                                                                |
|  +-- 출력 설정 --------------------------------------------+  |
|  |  출력 폴더: [./output/wav_files          ] [찾아보기..] |  |
|  |  [✓] 입력 파일과 같은 폴더에 저장                       |  |
|  |  중복 시: (●) 덮어쓰기  ( ) 건너뛰기  ( ) 번호 추가    |  |
|  +----------------------------------------------------------+  |
|                                                                |
|  변환 중: recording_02.raw  (2/5 파일)                        |
|  [================================          ] 60%              |
|                                                                |
|  [        변환 시작        ]       [     취소     ]           |
+---------------------------------------------------------------+
```

- 윈도우 크기: 750x600 (최소: `root.minsize(650, 500)`)
- 테마: `vista` (fallback: `winnative` → `clam`)
- Treeview가 수직 공간을 확장 점유 (`weight=1`)
- DPI 인식: `ctypes.windll.shcore.SetProcessDpiAwareness(1)` (Tk root 생성 전 호출)

---

## 5. 구현 순서

### Phase 1: 데이터 모델 + 핵심 엔진

1. `pcm2wav/__init__.py` — 패키지 초기화 (`__version__ = "0.1.0"`)
2. `pcm2wav/models.py` — `ByteOrder`, `PcmFormat`, `ConversionResult`, `PcmConversionError` 정의
3. `tests/conftest.py` — 테스트 픽스처 (known-pattern PCM 파일 생성기)
4. `tests/test_models.py` — PcmFormat 유효성 검증 테스트
5. `pcm2wav/converter.py` — `swap_byte_order()` 구현 + 테스트
6. `pcm2wav/converter.py` — `convert_8bit_signedness()` 구현 + 테스트
7. `pcm2wav/converter.py` — `validate_pcm_file()` 구현 + 테스트
8. `pcm2wav/converter.py` — `convert_pcm_to_wav()` 단일 변환 구현 + 테스트
9. `pcm2wav/converter.py` — `batch_convert()` 배치 변환 구현 + 테스트
10. `pcm2wav/presets.py` — 프리셋 정의 + 테스트

### Phase 2: GUI

11. `pcm2wav/widgets.py` — `ParameterPanel`
12. `pcm2wav/widgets.py` — `FileListPanel`
13. `pcm2wav/app.py` — 레이아웃 조립 + 출력 설정

### Phase 3: 통합

14. 상태 머신 구현 (IDLE/CONVERTING/COMPLETED/CANCELLED/ERROR)
15. 백그라운드 스레드 + `queue.Queue` 폴링
16. 진행률 표시 + `ttk.Progressbar`
17. 취소 + 부분 파일 삭제
18. 완료 요약 다이얼로그 + Treeview 상태 갱신
19. 키보드 단축키 바인딩

### Phase 4: 마무리

20. `vista` 테마 + fallback + DPI awareness + `root.minsize()`
21. `WM_DELETE_WINDOW` 핸들러
22. 로깅 설정 (`logging`, DEBUG, 콘솔 출력)
23. `main.py` 작성
24. `pyproject.toml` 작성

---

## 6. 알려진 제한 사항 (v1)

| 항목 | 설명 | 향후 계획 (v2) |
|------|------|----------------|
| 32-bit Integer PCM | 미지원. `wave` 모듈이 `WAVEFORMATEXTENSIBLE` 미사용 | 수동 WAV 헤더 작성 |
| 32-bit Float PCM | 미지원 (`wave` 모듈 한계) | 수동 WAV 헤더 작성 |
| WAVEFORMATEXTENSIBLE | 미사용. 24-bit에서 기본 fmt 청크만 사용 | 수동 헤더로 확장 |
| 4GB 초과 WAV | 미지원 (RIFF/data uint32 한계) | RF64/BW64 포맷 |
| 24-bit 호환성 | `wave` 모듈 버전별 처리 상이 가능. 재생 테스트 필수 | 수동 헤더로 안정화 |
| 드래그 앤 드롭 | 미지원 | tkinterdnd2 활용 |
| 오디오 미리듣기 | 미지원 | winsound 프리뷰 |
| mu-law / a-law | 미지원 | 룩업 테이블 변환 |
| 설정 저장 | 미지원 | config.json |
| 다채널 (5.1, 7.1) | 미지원 (Mono/Stereo만) | channels 확장 |

---

## 7. 테스트 계획

### 7.1 테스트 픽스처 전략 (`conftest.py`)

PCM 테스트 파일은 known-pattern 방식으로 생성:

| 패턴 | 용도 |
|------|------|
| 사인파 (440Hz, 1초) | WAV 변환 후 재생 확인 |
| 증가 바이트 패턴 (0x00~0xFF 반복) | 바이트 스왑/부호 변환 정확성 검증 |
| 모든 0x00 | 부호 변환 경계값 (signed 0x00 → unsigned 0x80) |
| 모든 0xFF | 부호 변환 경계값 (signed 0xFF → unsigned 0x7F) |
| 1프레임 파일 | 최소 파일 엣지 케이스 |
| 청크 경계 파일 | CHUNK_SIZE 정확한 배수 크기 |
| 프레임 미정렬 파일 | 잘림 처리 동작 확인 |

### 7.2 단위 테스트 (pytest)

| 카테고리 | 테스트 항목 |
|----------|------------|
| 모델 검증 | PcmFormat 기본값, sample_width, frame_size 계산 |
| 모델 검증 | `__post_init__` 검증: 잘못된 bit_depth, 범위 초과 sample_rate, 잘못된 channels, unsigned 16-bit |
| 바이트 스왑 | 16-bit array.byteswap, 24-bit 슬라이스 스왑, 8-bit no-op, 빈 버퍼 |
| 8-bit 부호 | translate 테이블 정확성, 경계값 (0x00→0x80, 0x7F→0xFF, 0x80→0x00) |
| 파일 검증 | 미존재 파일(error), 빈 파일(error), 프레임 미정렬(warning), 4GB 초과(error) |
| 단일 변환 | 16-bit LE mono, 16-bit BE mono, 8-bit signed, 8-bit unsigned, 24-bit LE stereo |
| 단일 변환 | WAV 헤더 검증: nchannels, sampwidth, framerate, nframes |
| 단일 변환 | 에러: 미존재 입력, 읽기 전용 출력, 빈 파일 |
| 단일 변환 | 취소 시 부분 파일 삭제 확인 |
| 배치 변환 | 다수 성공, 일부 실패 시 계속, 취소 시 중단 |
| 배치 변환 | progress_callback 호출 횟수/인자 정확성 |
| 엣지 케이스 | 1프레임 파일, 청크 경계 파일, 유니코드 경로 |
| 프리셋 | 모든 프리셋 유효성, 기본 프리셋 존재, dict 순서 보존 |

### 7.3 수동 테스트 (GUI)

1. 앱 실행 → 위젯 정상 렌더링 (DPI 스케일링 포함)
2. 프리셋 선택/Custom 전환 (필드 활성화/비활성화)
3. 8-bit 부호 필드 활성화, 16/24-bit에서 비활성화+Signed 고정
4. 파일/폴더 추가 → 목록 표시, 중복 방지
5. 다양한 확장자 (.pcm, .raw, .bin)
6. 변환 실행 → 진행률 → WAV 생성
7. 배치 취소 → 안전 중단 + 부분 파일 삭제
8. WAV 재생 확인 (특히 24-bit)
9. 덮어쓰기/건너뛰기/번호 추가 옵션
10. "같은 폴더" 체크박스 ↔ 출력 폴더 상호작용
11. 변환 중 윈도우 닫기 → 확인 다이얼로그
12. 빈 목록에서 변환 시작 → 버튼 비활성화
13. 키보드 단축키 (Ctrl+O, Delete, Enter, Escape)
14. vista 불가 시 fallback 테마

---

## 8. `main.py` 명세

```python
"""PCM to WAV Converter — 실행 진입점."""

import ctypes
import logging
import sys


def main() -> None:
    """앱 실행."""
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler()],
    )

    from pcm2wav.app import Pcm2WavApp

    app = Pcm2WavApp()
    app.run()


if __name__ == "__main__":
    main()
```

---

## 9. `pyproject.toml` 명세

```toml
[project]
name = "pcm2wav"
version = "0.1.0"
description = "PCM to WAV Converter GUI"
requires-python = ">=3.10"

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "SIM", "TCH"]

[tool.mypy]
python_version = "3.10"
strict = true
warn_return_any = true
warn_unused_configs = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v"
```

---

## 10. 핵심 파일 목록

| 파일 | 역할 | Phase |
|------|------|-------|
| `pcm2wav/__init__.py` | 패키지 초기화, `__version__` | 1 |
| `pcm2wav/models.py` | 데이터 타입 | 1 |
| `pcm2wav/converter.py` | 변환 엔진 | 1 |
| `pcm2wav/presets.py` | 프리셋 데이터 | 1 |
| `tests/conftest.py` | 테스트 픽스처 | 1 |
| `tests/test_models.py` | 모델 테스트 | 1 |
| `tests/test_converter.py` | 변환 테스트 | 1 |
| `tests/test_presets.py` | 프리셋 테스트 | 1 |
| `pcm2wav/widgets.py` | GUI 위젯 | 2 |
| `pcm2wav/app.py` | 메인 GUI | 2-3 |
| `main.py` | 실행 진입점 | 4 |
| `pyproject.toml` | 프로젝트 설정 | 4 |
