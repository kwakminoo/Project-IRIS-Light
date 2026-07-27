# 구현 프롬프트: Iris Control Surface + Hermes MCP/Tools + Skills

> 합의안 원문 보관. 구현 상태: 2026-07-24 반영.
> 운영 가이드: `integrations/hermes-skills/README.md`
> API: `docs/api/API-명세서.md` §6b

핵심 파일:

- `iris/system/control_surface.py` — HTTP 레지스트리
- `iris/ui/control_bindings.py` — MainWindow 액션 바인딩
- `iris/mcp/iris_control_stdio.py` — Hermes stdio MCP
- `integrations/hermes-skills/iris-control/*/SKILL.md`
