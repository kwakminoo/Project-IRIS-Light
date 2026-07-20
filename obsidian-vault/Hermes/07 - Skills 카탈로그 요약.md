# Hermes — Skills 카탈로그 요약

> Source: https://hermes-agent.nousresearch.com/docs/reference/skills-catalog  
> 정리일: 2026-07-20

Hermes는 설치 시 **~90개 bundled 스킬**을 `~/.hermes/skills/`에 복사합니다.  
추가 **~60 optional** 스킬은 Hub/별도 설치.

```bash
hermes skills list
hermes skills reset --restore   # 삭제된 bundled 복구
```

## 카테고리별 요약

### apple (macOS)

| 스킬 | 설명 |
|------|------|
| apple-notes | Apple Notes (memo CLI) |
| apple-reminders | Reminders (remindctl) |
| findmy | Find My 기기/AirTag |
| imessage | iMessage/SMS (imsg) |

### autonomous-ai-agents

| 스킬 | 설명 |
|------|------|
| claude-code | Claude Code CLI 위임 |
| codex | OpenAI Codex CLI |
| opencode | OpenCode CLI |
| hermes-agent | Hermes 자체 설정·기여 |

### computer-use

데스크톱 백그라운드 조작 (클릭·타이핑·스크롤) — macOS/Windows/Linux

### creative

architecture-diagram, excalidraw, manim-video, comfyui, p5js, humanizer, …

### email

| 스킬 | 설명 |
|------|------|
| **himalaya** | IMAP/SMTP 터미널 메일 (Gmail·Naver 다계정) |

### github

codebase-inspection, github-pr-workflow, github-code-review, github-issues, …

### note-taking

| 스킬 | 설명 |
|------|------|
| **obsidian** | Obsidian vault 읽기·검색·편집 |

### productivity

| 스킬 | 설명 |
|------|------|
| **google-workspace** | Gmail, Calendar, Drive, Docs, Sheets |
| notion | Notion API |
| airtable | Airtable |
| ocr-and-documents | PDF/스캔 OCR |
| powerpoint | .pptx |
| teams-meeting-pipeline | Teams 회의 요약 |
| maps | OSM 지오코딩·경로 |

### research

arxiv, blogwatcher (RSS), llm-wiki, polymarket, research-paper-writing

### software-development

| 스킬 | 설명 |
|------|------|
| **plan** | 실행 없이 `.hermes/plans/`에 계획만 작성 |
| test-driven-development | TDD RED-GREEN-REFACTOR |
| systematic-debugging | 4단계 디버깅 |
| requesting-code-review | 커밋 전 리뷰 |
| spike | 실험·검증 |
| simplify-code | 3-agent 병렬 정리 |

### mlops

huggingface-hub, vllm, llama-cpp, weights-and-biases, audiocraft, SAM

### media

gif-search, youtube-content, heartmula (음악 생성)

### smart-home

openhue (Philips Hue)

### social-media

xurl (X/Twitter CLI)

---

## 스킬 사용 패턴

```bash
/plan migrate auth to OAuth2
/github-pr-workflow open PR for feature X
/himalaya show last 5 unread from naver account
/obsidian search "Ollama"
/learn https://docs.example.com/api
```

스택 (최대 5):

```bash
/github-pr-workflow /test-driven-development fix #42
```

---

## Iris Light에서 활용

| Iris 기능 | 연관 Hermes 스킬 |
|-----------|------------------|
| Obsidian Wiki | `obsidian` |
| (예정) Email | `himalaya`, Email Gateway |
| 채팅 코딩 | `plan`, `github-pr-workflow` |
| Ollama 문서 vault | `obsidian`, `llm-wiki` |

---

## Optional Skills & Hub

- Optional catalog: ~60 추가 스킬
- Skills Hub: 커뮤니티 공유 (agentskills.io 호환)
- `/learn` — URL·로컬·대화에서 스킬 자동 생성

관련: [[02 - 핵심 기능 (도구·메모리·스킬)]] · [[06 - 이메일과 생산성 스킬]]
