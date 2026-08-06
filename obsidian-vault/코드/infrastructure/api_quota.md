# api_quota

`iris/infrastructure/api_quota.py`

외부 API 월 할당량(검색·크레딧) 조회.

## 주요 정의

- `class ApiQuota`
- `def _hermes_env_path`
- `def _parse_dotenv`
- `def _env_get`
- `def _get_json`
- `def fetch_serpapi_quota`
- `def fetch_firecrawl_quota`
- `def fetch_api_quotas`
- `def format_quota_pair`

## 내부 의존성

- [[ollama_usage]]
