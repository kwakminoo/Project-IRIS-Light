# pinned_monitor

`iris/monitoring/pinned_monitor.py`

고정된 창을 주기적으로 캡처해 모델로 분석하고 상태 변화를 보고하는 서비스.

## 주요 정의

- `def status_label`
- `class PinnedMonitorService`

## 내부 의존성

- [[activity_sink]]
- [[models]]
- [[ollama_client]]
- [[pin_store]]
- [[screen_capture]]
- [[settings]]
- [[state_detector]]
- [[window_controller]]
