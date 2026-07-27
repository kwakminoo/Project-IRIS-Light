# Hermes — MCP 연동

> Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp  
> 정리일: 2026-07-20

## MCP란?

**Model Context Protocol (MCP)** — Hermes가 **외부 도구 서버**에 연결해 GitHub, DB, 파일시스템, 내부 API 등의 도구를 **네이티브 도구처럼** 사용하게 합니다.

Iris Light는 MCP를 **직접** 쓰지 않고, **Hermes가 MCP를 대신 연결**합니다.

```
[Hermes Agent]
    ├─ built-in tools (terminal, web, …)
    └─ MCP discover_mcp_tools()
           ├─ stdio server (npx, uvx, …)
           └─ HTTP server (remote URL)
```

## MCP가 주는 것

- 외부 도구 생태계 접근 (Hermes 네이티브 도구 작성 불필요)
- **stdio** + **HTTP** 동일 config
- 시작 시 **자동 도구 발견·등록**
- **서버별 도구 필터** (`include` / `exclude`)
- Resource·Prompt 유틸리티 래퍼

## 빠른 시작

`~/.hermes/config.yaml`:

```yaml
mcp_servers:
  filesystem:
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-filesystem", "C:/Users/you/projects"]
```

```bash
hermes chat
# "List files in projects and summarize structure"
```

설정 변경 후: `/reload-mcp` (재시작 없이)

## 두 가지 전송 방식

### 1) Stdio (로컬 subprocess)

```yaml
mcp_servers:
  github:
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-github"]
    env:
      GITHUB_PERSONAL_ACCESS_TOKEN: "***"
    timeout: 120
    connect_timeout: 60
```

**적합:** 로컬 설치, 낮은 지연, npx/uvx 기반 서버

### 2) HTTP (원격)

```yaml
mcp_servers:
  remote_api:
    url: "https://mcp.example.com/mcp"
    headers:
      Authorization: "Bearer ***"
    auth: oauth          # Linear, Sentry 등 OAuth 2.1
```

**적합:** 호스팅된 MCP, 사내 API, subprocess 불필요

### OAuth HTTP 예 (Linear)

```yaml
mcp_servers:
  linear:
    url: "https://mcp.linear.app/mcp"
    auth: oauth
```

첫 연결 시 브라우저 인증 → 토큰 `~/.hermes/mcp-tokens/*.json`

## 카탈로그 (원클릭 설치)

Nous 검수 MCP 목록:

```bash
hermes mcp                # 대화형 선택
hermes mcp catalog        # 텍스트 목록
hermes mcp install n8n    # 이름으로 설치
hermes mcp configure linear   # 도구 선택 변경
hermes mcp login googledrive  # OAuth 로그인
```

예시 항목: `n8n`, `linear`, `github`, …

설치 시 **도구 체크리스트**로 expose할 tool만 선택.

## 도구 필터링

```yaml
mcp_servers:
  github:
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-github"]
    tools:
      include: ["create_issue", "search_repositories"]
      exclude: ["delete_repository"]
```

- `include` — 허용 목록만
- `exclude` — 제외
- utility wrapper (resources/prompts) 정책도 설정 가능

## MCP Config 주요 키

| 키 | 설명 |
|----|------|
| `command` / `args` / `env` | stdio 서버 |
| `url` / `headers` | HTTP 서버 |
| `auth: oauth` | OAuth 2.1 + PKCE |
| `enabled: false` | 서버 비활성 |
| `timeout` | 도구 호출 타임아웃 (기본 300s) |
| `connect_timeout` | 연결 타임아웃 (기본 60s) |
| `client_cert` / `client_key` | mTLS |
| `tools.include` / `exclude` | 도구 필터 |

참고: [MCP Config Reference](https://hermes-agent.nousresearch.com/docs/reference/mcp-config-reference)

## Iris Light + MCP 사용 시나리오

1. Hermes `config.yaml`에 Gmail/Drive/Notion MCP 등록
2. **Iris UI 역제어:** `iris-control` MCP (`py -m iris.mcp.iris_control_stdio`) — 설치는 `integrations/hermes-skills/README.md`
3. `hermes gateway` 실행
4. Iris Light 채팅 (`IRIS_HERMES_ENABLED=1`)에서 자연어 요청
5. Hermes가 MCP 도구 호출 → Iris Live Activity에 `[tool]` / `Iris control:` 진행 표시

Iris는 **MCP 설정·필터링을 Hermes에 위임** — Iris 코드에 MCP 클라이언트 추가 불필요.  
Iris Control Surface는 **서버** 역할만 (Hermes → Iris).

## 권장 첫 MCP 서버

| 서버 | 용도 |
|------|------|
| `@modelcontextprotocol/server-filesystem` | 로컬 파일 |
| `@modelcontextprotocol/server-github` | GitHub PR/Issue |
| `chrome-devtools-mcp` | WSL↔Windows Chrome (WSL2) |
| Linear / Notion (catalog) | 이슈·문서 |

## 트러블슈팅

| 증상 | 해결 |
|------|------|
| 서버 연결 실패 | `connect_timeout` 증가, npx/Node 설치 확인 |
| OAuth 타임아웃 | `hermes mcp login <name>` 별도 터미널에서 (5분 대기) |
| Google Drive 무반응 | DCR 미지원 → `oauth.client_id`/`client_secret` 수동 설정 |
| 도구 안 보임 | `/reload-mcp`, `tools.include` 확인 |

## 관련 문서

- [Use MCP with Hermes (실전 가이드)](https://hermes-agent.nousresearch.com/docs/guides/use-mcp-with-hermes)
- [Build a Hermes Plugin](https://hermes-agent.nousresearch.com/docs/guides/build-a-hermes-plugin)
- [Integrations Overview](https://hermes-agent.nousresearch.com/docs/integrations/)

관련: [[02 - 핵심 기능 (도구·메모리·스킬)]] · [[05 - API Server와 Iris Light 연동]]
