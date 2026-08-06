# settings_service

`iris/ui/settings/settings_service.py`

SettingsDialog가 쓰는 Qt-비의존 로직 (음성 런타임 호출, 프로필 검증).

## 주요 정의

- `def confirm_voice_reference`
- `def ensure_voice_hash_for_test`
- `def load_hermes_sync_status_text`
- `def build_profile_update`

## 내부 의존성

- [[hermes_iris_control_sync]]
- [[user_profile]]
- [[voice_prefs]]
- [[voice_runtime_client]]
