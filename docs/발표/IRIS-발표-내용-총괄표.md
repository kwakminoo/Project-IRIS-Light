# IRIS 발표 자료 — 내용 총괄표

| 항목 | 내용 |
|------|------|
| 문서 성격 | 발표용 PPT 구성 자료(공문서 형식 정리) |
| 대상 사업·과제 | IRIS(Iris Light) — Open Source Desktop AI Agent Runtime |
| 작성 기준일 | 2026-09-18 |
| 앱 버전 | `0.1.0-light` |
| 최신 공개 릴리스 | IRIS Light v2026.08.27 |
| 근거 자료 | `README.md`, `docs/domain.md`, `docs/ia/IA.md`, `docs/installer-release.md`, `LICENSE.md`, `docs/code-review/조치-소요-사항-총괄표.md`, GitHub 공개 저장소·릴리스, 소개 사이트 |
| 비고 | 본 문서는 발표 슬라이드 초안용 내용 목록이며, 수치·일정·발표 실적은 공개 문서에 확인된 범위로 한정함 |

---

## 0. 발표 구성 일람

| 연번 | 발표 항목 | 핵심 메시지(한 줄) |
|:---:|-----------|-------------------|
| 1 | 배경 및 취지 | AI 활용의 진입 장벽을 낮추고, PC에서 실행 가능한 오픈소스 에이전트 런타임을 제공한다. |
| 2 | 기존의 문제점 | 벤더 종속, 대화형 챗봇 한계, 로컬 모델 연동 복잡, 설치·음성·도구 확장의 파편화 |
| 3 | 해결하고자 하는 내용 | HUD·게이트웨이·설치 프로토콜로 Ollama·Hermes·MCP·음성을 하나의 데스크톱 런타임으로 통합 |
| 4 | 타인에게 유용한 이유 | 학생·취준생·초보 개발자·로컬 프라이버시 중시 이용자의 실습형 AI 작업 환경 제공 |
| 5 | 기반 확장·성취 가능성 | 스킬·MCP·IDE·다이어그램·보이스·에뮬레이터 등을 토대로 도메인 에이전트·교육·자동화 제품화 |
| 6 | 쉬운 설치 및 환경 | `IRIS-Setup.exe` 단일 설치 + 시작 위저드, GPU 불필요(클라우드 모델 기본) |
| 7 | 동작 주요기능 | 에이전트 실행, 음성, IDE Companion, 워크스페이스, Control Surface, 로컬/클라우드 모델 |
| 8 | 개발 문서 | 도메인·IA·API·음성·설치·데모 대본 등 체계적 기술 문서 |
| 9 | 오픈소스 생태계 활동 | Ollama·Hermes·Theia·Open VSX·MCP 등 기존 생태계와의 연동·기여 가능 구조 |
| 10 | 주요 발표 및 공개 활동 | GitHub 공개, 릴리스·설치본 배포, 다국어 README, 소개 사이트 |
| 11 | 라이선스 | GPL-3.0-or-later (PyQt6 결합 저작물 요건 충족) |
| 12 | 향후 계획 | 플러그인 마켓·커뮤니티 스킬·멀티에이전트·클라우드 런타임 등 |

---

## 1. 배경 및 취지

| 구분 | 내용 |
|------|------|
| 프로젝트 정의 | IRIS는 LLM·MCP·Voice Runtime·로컬/클라우드 모델을 연결하여 **이용자 PC에서 실행되는 오픈소스 데스크톱 AI Agent Runtime**이다. |
| 추진 배경 | 기존 AI 어시스턴트는 특정 서비스 구독·벤더에 종속되거나 대화 인터페이스에 머무르는 경우가 많으며, 로컬 모델만으로는 코딩·문서·파일 작업까지 이어지기 어렵다. |
| 사업·교육적 취지 | 유료 구독 및 복잡한 수동 연동 없이, 설치 프로그램 하나로 Ollama(모델 추론)와 Hermes Agent(도구·스킬)를 준비하고 대화형 HUD로 통합한다. |
| 기대 효과 | (1) 접근성 제고 (2) 실습형 AI 활용 역량 강화 (3) 경제적·디지털 격차로 인한 AI 경험 불평등 완화 (4) 로컬 실행을 통한 프라이버시·자립성 확보 |
| 설계 원칙 | 웹검색·셸·파일 IO를 자체 재구현하지 아니하고, **세션·권한·스트리밍 UI·시작 프로토콜**을 담당하며 실행은 Ollama/Hermes에 위임한다. |

---

## 2. 기존의 문제점

| 연번 | 문제 유형 | 구체적 현황 |
|:---:|-----------|-------------|
| 1 | 벤더 종속 | 특정 클라우드 AI 서비스·구독에 묶여 모델·도구·요금 정책 변경에 취약함 |
| 2 | 인터페이스 한계 | 대화형 챗봇에 머물러 실제 PC의 파일·터미널·브라우저 작업으로 이어지지 못함 |
| 3 | 로컬 모델의 미완결성 | 모델 추론만 가능하고, 에이전트·도구·MCP·UI를 직접 연동해야 하는 부담이 큼 |
| 4 | 설치·환경 복잡 | Python·가상환경·의존성·에이전트 게이트웨이·모델 pull 등 수동 절차가 다단계임 |
| 5 | 하드웨어 장벽 | 로컬 LLM 중심으로 설계된 경우 GPU·VRAM 요구로 저사양 PC 이용이 곤란함 |
| 6 | 음성·도구의 파편화 | STT/TTS·외부 도구가 앱에 강하게 결합되거나, 확장 경로(MCP·스킬)가 부재함 |
| 7 | 실행 경계 부재 | 에이전트 로직이 UI에 혼재되어 유지보수·권한·세션 관리가 어려움 |

---

## 3. 해결하고자 하는 내용

| 연번 | 해결 목표 | IRIS의 대응 방식 |
|:---:|-----------|------------------|
| 1 | 벤더 비종속 모델 연결 | Ollama 및 OpenAI 호환 provider를 선택·연결 |
| 2 | 에이전트 실행 경계 분리 | Runtime Gateway로 세션·권한·스트리밍을 담당하고, 도구 실행은 Hermes에 위임 |
| 3 | 저사양 PC 이용 가능 | 클라우드 모델을 기본으로 두고, 로컬 모델은 선택 사항으로 운영 (GPU 불필요) |
| 4 | 음성 독립 운용 | Voice Runtime을 별도 FastAPI 서비스(`:18765`)로 분리(선택 설치) |
| 5 | 도구·스킬 확장 | Hermes 스킬 및 MCP(`iris-control` 등)로 확장 |
| 6 | 설치·온보딩 자동화 | `IRIS-Setup.exe`·`setup.ps1`/`setup.sh` 및 시작 위저드(Setup Protocol)로 Ollama·Hermes·provider·gateway를 단계 자동화 |
| 7 | 데스크톱 HUD 통합 | 채팅·모니터·위키·메일·캘린더·IDE Companion 등을 단일 PyQt6 HUD로 제공 |
| 8 | 에이전트→UI 역제어 | Control Surface(`:8765`) 및 iris-control 스킬로 Hermes가 UI·세션·바이브코딩을 제어 |

---

## 4. 이 프로젝트가 다른 사람들에게 유용한 이유

| 이용 대상 | 유용성 |
|-----------|--------|
| 학생·취준생 | 구독료·복잡한 에이전트 셋업 없이 로컬 PC에서 AI 실습·과제·포트폴리오 작업이 가능함 |
| 초보 개발자 | 자연어로 파일 작성·터미널 실행·IDE 연동까지 체험하며 도구 호출·MCP 개념을 학습할 수 있음 |
| 교육·연구 기관 | 오픈소스·GPL 조건으로 수업·실습 환경에 배포·개작·재배포가 가능함 |
| 개인·소규모 팀 | 메일·캘린더·위키·시스템 모니터 등 워크스페이스와 에이전트를 한 화면에서 운용함 |
| 프라이버시 중시 이용자 | 로컬 실행·로컬 SQLite 저장(`~/.iris-light/`)으로 민감 정보의 외부 전송을 줄일 수 있음 |
| 오픈소스 기여자 | 스킬·MCP·플러그인·체크 스크립트 단위로 기여·포크가 용이함 |
| 타 프로젝트 개발자 | Runtime Gateway·Control Surface·설치 프로토콜 패턴을 참고하여 자체 에이전트 HUD를 구축할 수 있음 |

---

## 5. 이 프로젝트를 사용하는 것 보다, 이를 기반으로 무엇을 더 개발·성취할 수 있는지

| 연번 | 확장 방향 | 기반 구성요소 | 기대 성취 |
|:---:|-----------|---------------|-----------|
| 1 | 도메인 전용 에이전트 | Hermes 스킬·MCP | 교육·행정·연구실·스타트업 업무에 맞춘 전용 도구 체인 구축 |
| 2 | IDE·바이브코딩 제품화 | IRIS IDE(Theia)·브리지·80:20 Companion 타일 | 대화형 코딩·자동 폴더 개방·터미널 연동형 개발 환경 고도화 |
| 3 | 시각화·설계 산출물 | archify 다이어그램 렌더러(`diagram.render`) | 아키텍처·시퀀스·워크플로 문서 자동 생성 파이프라인 |
| 4 | 음성 비서·접근성 | Voice Runtime(STT/TTS) | 핸즈프리 조작·알림 낭독·교육용 음성 인터페이스 |
| 5 | 모바일·UI 자동화 | Android 에뮬레이터·mobile-mcp·Aloha 화면학습 | 앱 테스트·RPA·모바일 QA 에이전트 |
| 6 | 지식 운영 체계 | Iris Wiki·Obsidian vault | 팀 지식베이스와 에이전트 질의응답의 결합 |
| 7 | 커뮤니티·마켓 | 로드맵의 Plugin Marketplace·Community Skills | 스킬·플러그인 유통 생태계 조성 |
| 8 | 멀티에이전트·클라우드 | Multi-Agent Collaboration·Cloud Runtime(계획) | 협업형·원격 실행형 에이전트 플랫폼으로 발전 |

> **요지:** IRIS는 “완성된 단일 챗봇”이 아니라 **확장 가능한 데스크톱 에이전트 런타임 프레임**이므로, 이용·포크 후 스킬·MCP·워크스페이스·IDE를 결합하여 고유 제품·교육과정·연구 플랫폼을 성취할 수 있다.

---

## 6. 쉬운 설치 및 환경

### 6.1 설치 방법

| 방법 | 절차 요약 | 권장 대상 |
|------|-----------|-----------|
| A. 설치 프로그램 | [IRIS-Setup.exe](https://github.com/kwakminoo/Project-IRIS-Light/releases/latest/download/IRIS-Setup.exe) 내려받기 → 실행 → 자동으로 Python·venv·패키지 준비 → 바탕화면 `IRIS` 실행 | 일반 이용자(권장) |
| B. 소스 자동 설치 | 저장소에서 `setup.bat`(Windows) 또는 `setup.sh`(Linux/macOS) 실행 | 개발자·기여자 |
| C. 수동 설치 | `venv` 생성 → `pip install -r requirements.txt` → `.env` 구성 | 환경 커스터마이징 필요 시 |

### 6.2 첫 실행(시작 위저드)

| 단계 | 내용 |
|------|------|
| Core | Ollama 설치·기동 → 최소 모델 pull → Hermes 설치 → API/provider 연결 → gateway 기동 |
| Optional | STT 음성·Full TTS·Aloha·에뮬레이터·Node/mobile-mcp·클라우드 로그인 등 「설치」또는 「나중에」선택 |
| 이후 | HUD 채팅에서 자연어 요청 → Hermes/Ollama가 응답·도구 실행을 스트리밍 |

### 6.3 권장 환경(클라우드 모델 위주)

| 구분 | 최소 | 권장 |
|------|------|------|
| OS | Windows 10/11 64bit | Windows 11 |
| CPU | 듀얼~쿼드코어 | i5 / Ryzen 5 이상 |
| RAM | 8GB | 16GB |
| GPU | **불필요** | 불필요 |
| 저장(IRIS 관련) | 여유 약 20GB | 여유 약 30GB |
| 네트워크 | 인터넷 연결 | 지연이 낮은 안정 회선 |
| Python | 3.11+ | 3.11+ |

### 6.4 설치상 유의사항

| 사항 | 안내 |
|------|------|
| SmartScreen | 코드 서명 인증서 부재로 Windows가 1회 경고할 수 있음 → 「추가 정보 → 실행」 |
| 설치 규모 | 설치본 약 23MB 수준(Setup), 패키지 수신에 수분 소요 |
| 복구 | 설치 중단 시 설치 폴더의 `setup.bat` 재실행으로 이어받기 가능 |
| 로그 | `setup-log.txt` · `setup-log-pip.txt` · `%LOCALAPPDATA%\iris-light\launcher.log` |

---

## 7. 동작 주요기능

| 기능 | 설명 | 비고 |
|------|------|------|
| LLM Agent Runtime | Hermes를 통한 멀티스텝 도구 호출(파일·터미널·웹) | Hermes 필수 구성요소 |
| MCP 연동 | `iris-control` stdio MCP · Hermes MCP | 외부 도구 확장 |
| Voice Runtime | STT/TTS 독립 FastAPI 서비스(`:18765`) | 선택 설치 |
| Runtime Gateway | 세션·권한·스트리밍 UI·실행 경계 | Ollama/Hermes 어댑터 |
| Local Model | Ollama 로컬 모델(`:11434`) | 선택 |
| Cloud Model | OpenAI 호환 provider(GPU 없는 PC용) | 기본 운용 경로 |
| 시작 프로토콜 | 첫 실행 시 Ollama·Hermes·provider·gateway·MCP 단계 자동화 | Setup Protocol |
| 대화형 HUD | 모델 선택, 이력, 사고/도구 로그, 실시간 스트리밍 | PyQt6 |
| Control Surface | Hermes → UI 역제어(`:8765`) · iris-control 스킬 | 바이브코딩·UI 제어 |
| 워크스페이스 | 시스템 모니터 · 이메일(다중 계정) · 캘린더 · IDE Companion · Iris Wiki | 구현 |
| IDE Companion | Eclipse Theia 기반 IRIS IDE · 브리지 · 80:20 타일 | Companion 모드 |
| 다이어그램 렌더 | archify 연동(`diagram.render`) | 아키텍처 등 HTML 산출 |
| 로컬 저장 | 설정·프로필 등 SQLite(`~/.iris-light/`) | 로컬 우선 |
| 선택 확장 | 화면 학습(Aloha) · Android 에뮬레이터 · mobile-mcp | Optional |
| 준비 중 | Instagram / Discord / Kakao / Telegram 워크스페이스 | stub |

### 7.1 핵심 데이터 흐름(요약)

| 순서 | 경로 |
|:---:|------|
| 1 | 이용자 자연어/음성 → IRIS HUD |
| 2 | Runtime Gateway → Hermes(`:8642`) |
| 3 | Hermes → Ollama(또는 클라우드 provider) 추론 |
| 4 | 필요 시 도구·스킬·MCP·터미널 실행 |
| 5 | 스트림 → 채팅 UI · Live Activity (+ 선택 TTS) |
| 6 | 역제어 시 Hermes → Control Surface(`:8765`) → UI |

---

## 8. 개발 문서

| 문서 경로 | 내용 |
|-----------|------|
| `docs/domain.md` | 바운디드 컨텍스트 · Runtime Gateway · 도메인 모델 |
| `docs/ia/IA.md` | 정보 구조 · 요청 경로 · 아키텍처 다이어그램 |
| `docs/api/` · `docs/api/API-명세서.md` | API 관련 명세 |
| `docs/voice.md` | 음성 STT/TTS · 보이스 프로필 |
| `docs/voice_architecture.md` | 음성 런타임 경계 · 흐름 |
| `docs/installer-release.md` | 설치 프로그램 빌드 · 릴리스 절차 |
| `docs/demo-video-script.md` | 데모 영상 촬영 대본 · 업로드 절차 |
| `docs/code-review/조치-소요-사항-총괄표.md` | 코드 검토·조치 추적 대장 |
| `docs/prompts/` | 구현·복구용 프롬프트(모델 연동, IDE Companion, Control Surface 등) |
| `integrations/hermes-skills/README.md` | Iris Control Surface(Hermes ↔ UI) |
| `integrations/iris-ide/README.md` | IRIS IDE(Theia) 빌드·브리지 |
| `integrations/archify/README.md` | 다이어그램 렌더러 반입·계약 |
| `LICENSE` · `LICENSE.md` | GPL 전문 · 라이선스 근거·서드파티 인벤토리 |
| `THIRD_PARTY_NOTICES.md` | 서드파티 고지 |
| `README.md` 외 다국어 | 한국어·English·日本語·中文 |
| `obsidian-vault/` | 프로젝트 지식 베이스(Wiki 소스) |
| `_check_*.py` 스모크 | 모듈 단위 회귀·자체점검 스크립트 |

---

## 9. 오픈소스 생태계 활동

| 구분 | 내용 |
|------|------|
| 프로젝트 공개 | GitHub 저장소 `kwakminoo/Project-IRIS-Light` 공개 운영 |
| 업스트림 연동 | Ollama(모델), Hermes Agent(도구·스킬), Eclipse Theia(IDE), Open VSX(확장), MCP 표준 |
| 벤더링·고지 | archify(MIT), ShowUI-Aloha(Apache-2.0) 등 서드파티를 반입하고 라이선스 고지 |
| 기여 창구 | 이슈·PR 환영 · 변경 전 `_check_*.py` 스모크 권장 |
| 기여자 조건 | PR은 GPL-3.0-or-later 제공에 동의한 것으로 간주 · GPL 비호환 의존성 추가 불가 |
| 커뮤니티 방향 | Community Agent Skills · Plugin Marketplace(로드맵)로 스킬·플러그인 유통 확대 예정 |
| 다국어·문서화 | README 4개 언어 · 도메인/IA/API/음성 문서 · 데모·설치 문서 정비 |

---

## 10. 주요 발표 및 공개 활동

| 연번 | 활동 | 현황·근거 |
|:---:|------|-----------|
| 1 | 소스코드 공개 | GitHub `Project-IRIS-Light` (2026-07 생성, 지속 갱신) |
| 2 | 바이너리·설치본 배포 | GitHub Releases — `IRIS-Setup.exe` (latest 고정 URL) |
| 3 | 버전 릴리스 | 최신 공개 태그 **IRIS Light v2026.08.27** (앱 `0.1.0-light`) |
| 4 | 소개 사이트 | [cjh030906.github.io/iris-light-site](https://cjh030906.github.io/iris-light-site/) |
| 5 | 다국어 문서 공개 | README 한국어·영어·일본어·중국어 |
| 6 | 기술·운영 문서 공개 | domain · IA · API · voice · installer · demo script |
| 7 | 데모 영상 | 촬영 대본·업로드 절차 문서화 완료, 영상 공개 준비 중 |
| 8 | 학술·행사 발표 | **본 발표 자료 작성 시점 기준으로, 저장소에 기재된 공식 학술·행사 발표 실적은 별도 열거하지 않음.** 이후 실적 발생 시 본 표에 추가 기재 |

> 발표 시 필요하면 위 「공개 활동」을 타임라인 슬라이드로 재구성하고, 학술·해커톤·커뮤니티 발표 실적은 확정 후 보강한다.

---

## 11. 라이선스

| 항목 | 내용 |
|------|------|
| 프로젝트 라이선스 | **GNU General Public License v3.0 이상 (`GPL-3.0-or-later`)** |
| SPDX | `GPL-3.0-or-later` |
| 저작권 표기 | `Copyright (C) 2026 IRIS Project Contributors` |
| 전문 위치 | 저장소 루트 `LICENSE` |
| 근거 문서 | `LICENSE.md` (채택 이유·서드파티 호환성·전환 경로) |
| 채택 사유 | UI가 PyQt6(GPL-3.0-only)에 결합되어 배포 시 MIT/Apache-2.0 선택이 불가하며, GPLv3 제약 하에서 가장 허용적인 선택이 `GPL-3.0-or-later`임 |
| 이용자 권리·의무 | 복제·개작·재배포 가능(카피레프트) · 개작 배포 시 동일 라이선스·대응 소스 제공 의무 |
| 서드파티 | mutagen, pynput, soxr, ShowUI-Aloha, archify 등 GPLv3 호환 범위에서 운용 · `THIRD_PARTY_NOTICES.md` 고지 |
| 더 개방적 전환 경로 | PyQt6 → PySide6(LGPL) 전환 시 검토 가능(`LICENSE.md` §5) |

---

## 12. 향후 계획

### 12.1 구현 완료(현행)

| 항목 | 상태 |
|------|------|
| LLM Agent Runtime (Hermes 도구 호출·멀티스텝) | 완료 |
| Voice Runtime (STT/TTS · 선택 설치) | 완료 |
| MCP Integration (`iris-control` · Hermes MCP) | 완료 |
| Local/Cloud Model Support | 완료 |
| Installation System (`IRIS-Setup.exe` · setup 스크립트) | 완료 |
| IDE Companion · Control Surface · 워크스페이스 핵심 | 완료(고도화 지속) |

### 12.2 계획(로드맵)

| 우선 영역 | 계획 항목 | 비고 |
|-----------|-----------|------|
| 생태계 | Plugin Marketplace | 플러그인 유통 |
| 생태계 | Community Agent Skills | 커뮤니티 스킬 공유 |
| 런타임 | Multi-Agent Collaboration | 다중 에이전트 협업 |
| 런타임 | Cloud Runtime | 원격·클라우드 실행 |
| 배포 | Docker Deployment | 선택(데스크톱 앱이 주 형태이므로 필수 아님) |
| 워크스페이스 | SNS·메신저 연동 | Instagram / Discord / Kakao / Telegram 등 |
| 품질 | 구조 개선·채팅 표시 계약·브리지 신원 승계 등 | 코드 검토 총괄표 잔여 과제 반영 |
| 홍보 | 데모 영상·GIF 공개 | `docs/demo-video-script.md` · `assets/demo/` |

---

## 부록 A. 발표용 한 장 요약(슬라이드 카피)

| 슬라이드 | 권장 문구 |
|----------|-----------|
| 표지 | IRIS — Open Source Desktop AI Agent Runtime |
| 문제 | AI는 많으나, PC에서 “도구를 쓰는 에이전트”로 쓰기까지는 멀다. |
| 해결 | 설치 하나로 Ollama + Hermes + HUD를 묶는 로컬 에이전트 런타임 |
| 차별점 | 벤더 비종속 · GPU 불필요 · 음성·MCP·IDE Companion · GPL 오픈소스 |
| 확장 | 스킬·MCP·IDE·다이어그램을 기반으로 도메인 제품·교육·자동화를 성취 |
| 마무리 | 공개 저장소·설치본·문서로 누구나 시작·기여·개작할 수 있다. |

---

## 부록 B. 주요 URL

| 구분 | URL |
|------|-----|
| 저장소 | https://github.com/kwakminoo/Project-IRIS-Light |
| 최신 릴리스 | https://github.com/kwakminoo/Project-IRIS-Light/releases/latest |
| 설치 프로그램 | https://github.com/kwakminoo/Project-IRIS-Light/releases/latest/download/IRIS-Setup.exe |
| 소개 사이트 | https://cjh030906.github.io/iris-light-site/ |
| Hermes | https://hermes-agent.nousresearch.com/ |
| Ollama | https://ollama.com/ |

---

*본 총괄표는 발표 PPT 초안 작성용이며, 슬라이드 분량·시각 자료·데모 시나리오는 별도 편집한다.*
