# Prompt: P2 SOUL — Iris 페르소나 제품 홈 동기

새 Cursor 채팅에 아래 블록만 붙여 넣는다. P1 완료 후 실행.

```text
Context:
- /poteto-mode Bug fix
- 실측: ~/.iris-light/agent/SOUL.md 가 여전히
  "You are Hermes Agent, built by Nous Research."
- 레포 원본: integrations/hermes-soul/SOUL.md (# IRIS Light Persona / 아이리스)
- 코드: iris/system/hermes_soul_sync.py (ensure_soul, hermes_home)
- sync JSON / 레거시 %LOCALAPPDATA%\hermes 잔상으로 제품 홈 SOUL이 안 덮였을 가능성.

Goal:
1) ensure_soul() 가 제품 홈 iris_agent_home()/SOUL.md 만 본다 (레거시 혼선 제거).
2) 마커 "# IRIS Light Persona" 없으면 강제 갱신 (업스트림 Hermes SOUL을 current로 오인 금지).
3) Iris↔에이전트 sync / ensure_iris_agent_runtime 경로에서 SOUL 동기 1회 호출이 실제로 돈다.
4) 지금 당장 제품 홈 SOUL.md 를 Iris 원본으로 덮어쓴다 (백업 SOUL.md.bak-iris 유지).
5) 자검: 제품 SOUL에 Hermes Agent / Nous Research 없음, 아이리스 있음.

Constraints:
- Surgical. soul sync·호출부·짧은 자검만. 브랜드 전면 스윕은 P4.
- 커밋 금지. API 키 금지.

Verify:
- .venv\Scripts\python.exe -m iris.system.hermes_soul_sync
- 제품 SOUL.md 첫 줄이 IRIS Light Persona
```
