# Hermes plugins (Iris Light)

이 폴더는 Hermes에 설치하는 **웹 검색 백엔드** 소스입니다.

## SerpApi

```
integrations/hermes-plugins/web/serpapi/
  → 복사 → %LOCALAPPDATA%\hermes\hermes-agent\plugins\web\serpapi\
```

이미 설치됨. Hermes 업그레이드 후 사라지면 다시 복사하세요.

설정 (`%LOCALAPPDATA%\hermes\config.yaml`):

```yaml
web:
  search_backend: serpapi
  extract_backend: firecrawl
```

Env:

```env
SERPAPI_API_KEY=...
SERPAPI_DEFAULT_ENGINE=google
```

게이트웨이 재시작: `hermes gateway`
