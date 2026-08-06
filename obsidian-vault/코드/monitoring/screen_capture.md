# screen_capture

`iris/monitoring/screen_capture.py`

화면/창 캡처 (기본은 메모리만, 디스크 저장은 설정으로).

## 주요 정의

- `class CaptureResult`
- `def _bgra_to_rgb_fast`
- `def capture_full_screen`
- `def capture_region`
- `def _capture_window_by_hwnd_impl`
- `def capture_window_by_hwnd`
- `def capture_result_to_png_bytes`
- `def maybe_save_debug_screenshot`

## 내부 의존성

- [[settings]]
