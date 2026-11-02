# Iris Agent — MCP 연동

> 정리일: 2026-10-28

## 역할

Iris Agent가 MCP 호스트로 외부 도구 서버를 붙인다.  
Iris UI 역제어는 `iris-control` MCP → Control Surface `:8765` (비시드 compat).

## iris-control

| 도구 | 용도 |
|------|------|
| `iris_get_state` | UI/세션 상태 |
| `iris_get_catalog` | 액션 목록 |
| `iris_invoke` | Wiki · IDE · Email · Calendar 등 |

seed 액션은 native registry로 리다이렉트되어 `:8765`를 안 탈 수 있다.

## 설정

`~/.iris-light/agent/config.yaml`의 `mcp_servers`는 손으로 고치지 않는다. sync가 upsert 한다.

```powershell
py -3 -m iris.system.hermes_iris_control_sync --apply
```

관련: [[02 - 핵심 기능 (도구·메모리·스킬)]]
