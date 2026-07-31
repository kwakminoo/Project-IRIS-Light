# Hermes ↔ Iris Control Surface

Iris가 떠 있을 때만 동작한다. Hermes가 Iris UI를 **tool-calling**으로 조작한다.

## 자동 설치 (Iris 기동 시)

Iris 시작 시 `iris.system.hermes_iris_control_sync`가:

1. `%LOCALAPPDATA%\hermes\config.yaml`에 `mcp_servers.iris-control` upsert  
2. `skills/iris-control/{iris-work-start,iris-work-end,iris-session-status,iris-vibe-code}` 복사   
3. `memories/MEMORY.md`에 Iris control 힌트 append (1회)  
4. 설정이 바뀌었고 gateway가 이미 떠 있으면 `--replace` 재기동  

→ **Iris를 꺼도 Hermes 디스크에 남음** (재시작 유지).

수동:

```powershell
py -3 -m iris.system.hermes_iris_control_sync --apply
```

상태: `%USERPROFILE%\.iris-light\hermes_iris_control_sync.json`

## 도구

- `iris_get_state` / `iris_get_catalog` / `iris_invoke`

## 스모크

```powershell
py -3 -m iris.system.control_surface
py -3 iris\ui\_check_ide_control_scenarios.py
```
