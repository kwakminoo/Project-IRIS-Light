# api_providers

`iris/storage/api_providers.py`

커스텀 OpenAI 호환 API 등록 — user_preferences JSON.

## 주요 정의

- `class ApiProvider`
- `def parse_models_text`
- `def mask_api_key`
- `def guess_base_url`
- `def runtime_model_id`
- `def parse_runtime_model_id`
- `def is_api_runtime_model`
- `def _from_dict`
- `def load_api_providers`
- `def save_api_providers`
- `def get_api_provider`
- `def upsert_api_provider`
- `def delete_api_provider`
- `def mark_provider_status`
- `def ok_providers_for_picker`

## 내부 의존성

- [[database]]
