# Hermes — 자동화와 Gateway

> Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/  
> 정리일: 2026-07-20

## 1. Messaging Gateway

**한 gateway**로 20+ 플랫폼에서 Hermes와 대화.

```bash
hermes gateway setup    # 플랫폼 연결 마법사
hermes gateway          # gateway + API Server 시작
```

### 지원 플랫폼 (일부)

| 플랫폼 | 용도 |
|--------|------|
| Telegram | 봇 DM/그룹 |
| Discord | 봇 + Voice Mode |
| Slack | Socket Mode |
| WhatsApp | Baileys bridge |
| Signal | signal-cli |
| **Email** | IMAP/SMTP 어시스턴트 |
| SMS | Twilio |
| Matrix, Mattermost | 팀 채팅 |
| Home Assistant | 스마트홈 |
| Microsoft Teams, Google Chat | (플러그인/문서 참고) |
| Webhooks | GitHub/GitLab 이벤트 트리거 |

이메일 상세: [[06 - 이메일과 생산성 스킬]]

---

## 2. Cron (예약 작업)

자연어 또는 cron 표현식으로 **반복 작업**.

```bash
# 예: 매일 아침 브리핑
"Every weekday at 8am, summarize unread emails and post to Telegram"
```

- `cronjob` 도구: create / list / update / pause / resume / run / remove
- **스킬 첨부** 가능
- 결과를 **임의 플랫폼**으로 delivery

가이드: [Automate with Cron](https://hermes-agent.nousresearch.com/docs/guides/automate-with-cron)  
튜토리얼: [Daily Briefing Bot](https://hermes-agent.nousresearch.com/docs/guides/daily-briefing-bot)

---

## 3. Subagent Delegation

`delegate_task` — **격리된 자식 에이전트** 병렬 실행.

- 기본 3 concurrent subagents (설정 가능)
- 제한된 toolset·별도 터미널 세션
- 연구·코드리뷰·멀티파일 작업에 적합

---

## 4. Code Execution

`execute_code` — Python 스크립트에서 Hermes 도구를 **RPC**로 호출.

- 다단계 파이프라인을 **한 LLM 턴**으로 축소
- sandboxed 실행

---

## 5. Hooks

라이프사이클 지점에 커스텀 코드:

- Gateway hooks — 로깅, 알림, webhook
- Plugin hooks — 도구 가로채기, 메트릭, 가드레일

---

## 6. Batch Processing

수백~수천 프롬프트 **병렬** 실행 → ShareGPT 형식 trajectory (RL/평가용)

---

## 7. Kanban & Persistent Goals

| 기능 | 설명 |
|------|------|
| **Kanban** | SQLite 태스크 보드, 멀티 프로필 조율 |
| **Persistent Goals** | standing goal까지 자율 진행 (Ralph loop 스타일) |

---

## 8. ACP (에디터 연동)

VS Code, Zed, JetBrains 등 **ACP 호환 에디터** 안에서 Hermes 사용.

---

## Iris Light와 Gateway

| 구성 | 설명 |
|------|------|
| Iris UI | 데스크톱 HUD (PyQt6) |
| Hermes gateway | `:8642` API + (선택) Telegram 등 |
| 동시 사용 | Iris 채팅 + Telegram 봇이 **같은 Hermes** 사용 가능 |

Gateway만 켜두면 Iris는 API Server로 붙고, Telegram 등은 별 채널로 같은 에이전트와 대화합니다.

관련: [[05 - API Server와 Iris Light 연동]] · [[06 - 이메일과 생산성 스킬]]
