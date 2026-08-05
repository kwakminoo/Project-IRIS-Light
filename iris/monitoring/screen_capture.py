"""화면/창 캡처 (기본은 메모리만, 디스크 저장은 설정으로)."""

from __future__ import annotations

import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from iris.config.settings import Settings


@dataclass
class CaptureResult:
    """RGB bytes + 크기."""

    width: int
    height: int
    rgb_bytes: bytes


def _bgra_to_rgb_fast(bgra: bytes, w: int, h: int) -> bytes:
    """PIL의 C 디코더로 BGRA→RGB 변환 (Python 루프 대비 ~50× 빠름).

    실패 시 순수 Python 폴백.
    """
    try:
        from PIL import Image  # type: ignore

        img = Image.frombytes("RGB", (w, h), bgra, "raw", "BGRX")
        return img.tobytes()
    except Exception:
        rgb = bytearray(w * h * 3)
        for i in range(w * h):
            b, g, r = bgra[i * 4], bgra[i * 4 + 1], bgra[i * 4 + 2]
            rgb[i * 3] = r
            rgb[i * 3 + 1] = g
            rgb[i * 3 + 2] = b
        return bytes(rgb)


def capture_full_screen(_settings: Settings) -> Optional[CaptureResult]:
    """전체 화면 캡처. 실패 시 None."""
    try:
        import mss  # type: ignore

        with mss.mss() as sct:
            mon = sct.monitors[1]
            shot = sct.grab(mon)
            return CaptureResult(
                shot.width,
                shot.height,
                _bgra_to_rgb_fast(shot.bgra, shot.width, shot.height),
            )
    except Exception:
        return None


def capture_region(left: int, top: int, width: int, height: int) -> Optional[CaptureResult]:
    """지정 영역 캡처 (스크린 좌표 기준).

    주의: 다른 창에 가려진 부분은 검은색으로 캡처됩니다.
          가려진 창을 캡처하려면 ``capture_window_by_hwnd`` 사용.
    """
    try:
        import mss  # type: ignore

        with mss.mss() as sct:
            shot = sct.grab({"left": left, "top": top, "width": width, "height": height})
            return CaptureResult(
                shot.width,
                shot.height,
                _bgra_to_rgb_fast(shot.bgra, shot.width, shot.height),
            )
    except Exception:
        return None


def _capture_window_by_hwnd_impl(hwnd: int) -> Optional[CaptureResult]:
    """PrintWindow 실제 호출 (별도 스레드에서 실행 가능)."""
    if sys.platform != "win32":
        return None
    if hwnd <= 0:
        return None

    try:
        import win32gui  # type: ignore
        import win32ui  # type: ignore
        from ctypes import windll  # type: ignore
    except Exception:
        return None

    hwndDC = None
    mfcDC = None
    saveDC = None
    saveBitMap = None
    try:
        left, top, right, bot = win32gui.GetWindowRect(hwnd)
        w, h = right - left, bot - top
        if w <= 0 or h <= 0:
            return None

        hwndDC = win32gui.GetWindowDC(hwnd)
        mfcDC = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()
        saveBitMap = win32ui.CreateBitmap()
        saveBitMap.CreateCompatibleBitmap(mfcDC, w, h)
        saveDC.SelectObject(saveBitMap)

        # PW_RENDERFULLCONTENT = 0x00000002 (가려진 창·DWM 가속 창 포함)
        result = windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 2)
        bgra = saveBitMap.GetBitmapBits(True)  # bytes (BGRA, top-down)

        if result != 1:
            return None
        return CaptureResult(w, h, _bgra_to_rgb_fast(bytes(bgra), w, h))
    except Exception:
        return None
    finally:
        # GDI 리소스 정리 — 누수 방지
        try:
            if saveBitMap is not None:
                win32gui.DeleteObject(saveBitMap.GetHandle())
        except Exception:
            pass
        try:
            if saveDC is not None:
                saveDC.DeleteDC()
        except Exception:
            pass
        try:
            if mfcDC is not None:
                mfcDC.DeleteDC()
        except Exception:
            pass
        try:
            if hwndDC is not None:
                win32gui.ReleaseDC(hwnd, hwndDC)
        except Exception:
            pass


def capture_window_by_hwnd(
    hwnd: int,
    *,
    timeout_sec: float = 2.5,
) -> Optional[CaptureResult]:
    """HWND 기반 창 캡처 (Windows ``PrintWindow`` API).

    - 가려진 창도 캡처 가능 (mss는 화면에 보이는 영역만 캡처)
    - ``PW_RENDERFULLCONTENT (0x2)`` 사용 → Windows 8.1+ 에서 Chrome/Electron 등도 캡처
    - 일부 HWND에서 PrintWindow가 무한 대기할 수 있어 timeout_sec로 스레드 join 제한
    - 실패 시 None → 호출 측에서 ``capture_region`` 으로 폴백 권장
    """
    if timeout_sec <= 0:
        return _capture_window_by_hwnd_impl(hwnd)

    holder: list[Optional[CaptureResult]] = [None]

    def _run() -> None:
        holder[0] = _capture_window_by_hwnd_impl(hwnd)

    worker = threading.Thread(target=_run, name="iris-printwindow", daemon=True)
    worker.start()
    worker.join(timeout=timeout_sec)
    if worker.is_alive():
        return None
    return holder[0]


def capture_result_to_png_bytes(
    cap: CaptureResult, *, max_width: int = 0
) -> bytes | None:
    """CaptureResult → PNG bytes (Ranker 멀티모달 전송용, 디스크 저장 없음).

    max_width > 0 이면 가로가 그보다 클 때 비율을 유지해 축소한다.
    비전 모델은 이미지를 타일로 쪼개 토큰화하므로, 원본 해상도를 그대로
    보내면 토큰·메모리·지연이 급격히 늘어난다. 창 상태 판정에는 1024px
    정도면 진행률·에러 문구를 읽기에 충분하다."""
    try:
        import io

        from PIL import Image  # type: ignore

        img = Image.frombytes("RGB", (cap.width, cap.height), cap.rgb_bytes)
        if max_width > 0 and img.width > max_width:
            height = max(1, round(img.height * max_width / img.width))
            img = img.resize((max_width, height), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


def maybe_save_debug_screenshot(settings: Settings, cap: CaptureResult, path: Path) -> None:
    """store_screenshots=True일 때만 디스크 저장."""
    if not settings.store_screenshots:
        return
    try:
        from PIL import Image  # type: ignore

        img = Image.frombytes("RGB", (cap.width, cap.height), cap.rgb_bytes)
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(path)
    except Exception:
        pass
