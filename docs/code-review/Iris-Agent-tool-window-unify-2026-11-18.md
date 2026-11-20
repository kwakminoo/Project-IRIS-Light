# Iris Agent — 도구·창 표면 통일 (Phase 3)

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-CR-2026-11-18-AGENT-P3-SURFACE |
| 작성일 | 2026-11-18 |
| 관련 | Phase 0 PHASE4 grants, Phase 1 process NO-GO, sidecar file/terminal OFF |
| 대상 | Speak allowlist · nudge · InternalSidecar 기본 표면 |
| 목적 | 제품 표면만 맞추고, 프로세스 병합은 하지 않는다 |

## 1. 결론

Speak 카탈로그는 PHASE4(`grants=38`) 한 줄이다다. Hermes 내장 `file`/`terminal`은 꺼 둔다. 제품 엔진 기본은 `InternalSidecar`다. same-process AIAgent 병합은 Phase 1 NO-GO를 유지한다.

## 2. Twin 표

| 표면 | 맡는 일 | 판단 |
|---|---|---|
| Speak / PHASE4 | `project.write`·`read`·`list`, `ide.open_file`, rename, `dump_lab` 등 38 grants | 엔진 카탈로그 = 제품 도구 창 |
| MEMORY nudge | 위 grants를 SpeakTools로 가르침 (`write_file` / `open_file` / `list_files` gate) | 새 권한을 모델에 노출 |
| InternalSidecar | 자식 `_sidecar_main` + AIAgent | 기본. Qt 프로세스 병합 없음 |
| Hermes toolsets | `disabled_toolsets=[file, terminal]` | Speak `shell.run` / `project.*`만 씀 |

## 3. Process

| 항목 | 내용 |
|---|---|
| Phase 1 | **NO-GO** (`Iris-Agent-Phase1-process-go-nogo-2026-11-18.md`) |
| NOTICE / 라이선스 | 손대지 않음 |
| 하지 않은 일 | AIAgent same-process, Hermes file/terminal 재활성, 광역 UI 문자열 교체 |

## 4. 조치

1. 표면 통일 정본은 본 문서 + Phase 1 NO-GO다.
2. 기본 엔진은 InternalSidecar를 유지한다.
3. grants·nudge·sidecar disable 자검이 깨지면 표면 회귀로 본다.
