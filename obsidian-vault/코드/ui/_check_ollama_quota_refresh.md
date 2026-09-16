# _check_ollama_quota_refresh

`iris/ui/_check_ollama_quota_refresh.py`

Ollama 할당량 즉시 갱신·표시 자검 (단계별).

## 주요 정의

- `def _assert_format`
- `def _assert_cloud_detect`
- `def _assert_stale_cache_fallback`
- `def _assert_worker_immediate`
- `def _assert_cloud_polling_flag`
- `def _assert_manual_click`
- `def main`

## 내부 의존성

- [[api_quota]]
- [[api_quota_worker]]
- [[main_window]]
- [[ollama_usage]]
- [[system_metrics_panel]]
