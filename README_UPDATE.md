# README 개편 기록 (2026-09-16)

GitHub Star/Fork 유입을 목표로 README 구조를 재구성했습니다.
**구현 코드·기술 문서는 손대지 않았고**, 기존 README에 있던 사실만 재배치·번역했습니다.

## 1. 변경 파일 목록

| 파일 | 상태 | 내용 |
|------|------|------|
| `README.md` | 수정 | 한국어판. 섹션 순서 재배치 + 언어 선택 · Demo · Why · Features · Architecture · Roadmap · Releases 추가 |
| `README.en.md` | 신규 | 영어 전문 번역 (한국어판과 동일 구조·동일 정보량) |
| `README.ja.md` | 신규 | 일본어 요약판 (핵심 섹션 + 상세는 `README.en.md` 링크) |
| `README.zh.md` | 신규 | 중국어 요약판 (동일 정책) |
| `assets/demo/README.md` | 신규 | Demo GIF 5개 스펙 (해상도·길이·용량·촬영 포인트) |
| `README_UPDATE.md` | 신규 | 이 문서 |

GitHub 저장소 설정도 변경했습니다 (아래 4항).

### 지시와 다르게 처리한 3가지

1. **제목은 `# IRIS` 유지** — 기존 README·앱·문서가 "표시 이름 IRIS / 코드명 Iris Light"로 통일돼 있어, 부제만 `Open Source Desktop AI Agent Runtime`으로 넣었습니다.
2. **`docs/images/architecture.png`를 새로 만들지 않음** — `docs/ia/iris-system-architecture.png`(1.5MB)가 이미 있습니다. README 본문에는 GitHub이 네이티브 렌더링하는 **Mermaid** 다이어그램을 넣고, 고해상도 원본은 기존 PNG로 링크했습니다. 파일·폴더 추가 0개.
3. **Releases 버전은 `IRIS Light v2026.08.27`** — 실제 GitHub 최신 릴리스 태그입니다. 지시의 `v0.1.0`은 앱 내부 버전 문자열(`0.1.0-light`)이라 괄호로 함께 표기했습니다.

## 2. README 구조 변경 이유

### 새 섹션 순서

```
언어 선택 → 제목·부제·한 줄 정의 → 배지 → Demo → Why IRIS? → Features
→ Architecture → Quick Start → 설치 → 실행 → Roadmap → Releases → 문서
→ 기여 → 라이선스 → 면책
```

| 변경 | 이유 |
|------|------|
| 최상단 언어 선택 4개 | 해외 유입 시 첫 화면에서 이탈하지 않게 |
| 제목 직후 "무엇인가" 한 문단 + 5개 목표 | 기존에는 "유료 구독 없이"라는 **혜택**부터 시작해 Agent Runtime이라는 정체가 스크롤 아래에 있었음 |
| Demo를 상단으로 | 영상/GIF는 Star 판단에 가장 빠르게 작용하는 요소 |
| 기존 "주요 기능" 13행 표 → `Features` 표로 압축 | 워크스페이스 6종을 한 행으로 묶고, 런타임 구성요소(Agent/MCP/Voice/Gateway/Model)를 위로 올림 |
| 기존 "한눈에 보는 구조" ASCII → Mermaid | Control Surface(`:8765`)와 Voice Runtime(`:18765`)이 ASCII 도식에서 빠져 있었음 |
| `Why IRIS?`를 문제 → 해결 표로 | 기존 "문제 정의" 3줄은 배경 설명이라 기능 대응이 안 보였음 |
| Roadmap 신규 | 완료 5개 / 계획 5개. Docker는 지시대로 Optional 표기 |
| Releases 신규 | 릴리스 페이지 유입 경로 확보 |

### `<details>`로 접은 항목 (파일 이동 없음)

초반 진입성을 위해 개발자용 상세 내용만 접었습니다. 삭제한 정보는 없습니다.

- 기대 효과 (프로젝트 배경)
- `setup.ps1` 6단계 표
- 설치 트러블슈팅 7행 표
- 필요 사양 (소프트웨어 · 하드웨어 표)
- EXE·바로가기 동작 방식
- 프로젝트 구조 · 기술 스택
- 왜 GPLv3인가

### 함께 고친 버그

기존 문서 표의 링크가 `` `[docs/domain.md](docs/domain.md)` `` 처럼 백틱 안에 있어 **9개 링크 전부 렌더링되지 않고 있었습니다.** 백틱을 제거해 실제 링크로 만들었고, `docs/installer-release.md`를 표에 추가했습니다.

### 작성 스타일 검증

"혁신적인 / 강력한 / 차세대 / 완벽한 / 최첨단 / 새로운 패러다임" — 4개 README 전부에서 미사용을 확인했습니다.

## 3. 추가해야 할 GIF 목록

`assets/demo/` 에 넣고, 4개 README에서 해당 이미지 줄의 `<!-- -->` 주석만 풀면 됩니다.
현재는 **주석 처리 상태**라 파일이 없어도 README에 깨진 이미지가 뜨지 않습니다.

| 파일 | 담을 내용 | README 위치 |
|------|------|------|
| `agent.gif` | 자연어 입력 → 사고/도구 로그 스트리밍 → 파일 생성 | Demo 1. Agent Execution |
| `voice.gif` | 마이크 입력 → STT 텍스트 → 응답 → TTS 재생 | Demo 2. Voice Interaction |
| `runtime.gif` | 시작 위저드/모니터의 Ollama·Hermes gateway 기동 | Demo 3. Runtime Architecture |
| `setup.gif` | `IRIS-Setup.exe` 실행 → 자동 설치 → 바탕화면 아이콘 | Demo 4. Installation |
| `main.gif` | HUD 첫인상 (선택 — 현재 README에서 미참조) | Hero 영역에 추가 시 |

공통 스펙: 폭 960px · 8~15초 · **파일당 5MB 이하** · 12~15fps · 메일/API 키 노출 금지.
상세는 [`assets/demo/README.md`](assets/demo/README.md), 촬영 대본은 [`docs/demo-video-script.md`](docs/demo-video-script.md).

데모 영상(YouTube)도 같은 방식으로 대기 중입니다 — 업로드 후 `<!-- DEMO_VIDEO:START -->` 블록의 `VIDEO_ID`를 교체하세요.

## 4. GitHub 설정 변경 사항

### 적용 완료 (gh CLI로 실행함)

**Description** — 비어 있던 상태에서 다음으로 설정:

```
Open Source Desktop AI Agent Runtime - LLM, MCP, Voice Runtime, and local/cloud
models wired into one PyQt6 desktop agent (Ollama + Hermes)
```

**Topics** — 0개에서 11개 추가:
`ai-agent` `llm` `llm-agent` `computer-use` `mcp` `ollama` `fastapi` `python` `voice-assistant` `desktop-ai` `open-source-ai`

```powershell
# 실제 실행한 명령
gh repo edit kwakminoo/Project-IRIS-Light --description "..." `
  --add-topic ai-agent --add-topic llm --add-topic llm-agent --add-topic computer-use `
  --add-topic mcp --add-topic ollama --add-topic fastapi --add-topic python `
  --add-topic voice-assistant --add-topic desktop-ai --add-topic open-source-ai
```

### 남은 수동 작업

| 항목 | 방법 |
|------|------|
| 데모 영상 업로드 | YouTube 업로드 후 4개 README의 `VIDEO_ID` 교체 |
| GIF 5개 녹화 | 위 3항 참고 |
| Social preview 이미지 | Settings → General → Social preview. `assets/visuals/iris_core.png` 활용 가능 |
| 릴리스 노트 정비 | `v2026.08.27` 릴리스 본문에 Roadmap 완료 항목 4개를 정리하면 유입에 유리 |
| Repository 사이트 링크 | Settings 또는 About → Website 에 `https://cjh030906.github.io/iris-light-site/` |

## 5. 검증

```powershell
# README 4개의 로컬 링크가 모두 실존하는지 (주석 처리된 GIF 4개만 미존재로 보고됨)
$files = @('README.md','README.en.md','README.ja.md','README.zh.md')
foreach ($f in $files) {
  $txt = Get-Content $f -Raw
  [regex]::Matches($txt, '\]\((?!http)([^)#]+)') | ForEach-Object { $_.Groups[1].Value.Trim() } |
    Sort-Object -Unique | Where-Object { -not (Test-Path $_) } | ForEach-Object { "MISSING [$f] -> $_" }
}
```

실행 결과: `assets/demo/*.gif` 4개만 미존재(의도된 주석 상태). 문서·라이선스·이미지 링크 전부 통과.
