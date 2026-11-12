# Iris vs Hermes 능력 벤치마크 결과 (4페이즈)

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-BENCH-20261109-120B |
| 작성일 | 2026-11-09 |
| 관련 | `scripts/iris_hermes_bench/`, run `20261109T082302Z` |
| 대상 | 동일 모델 `gpt-oss:120b-cloud` (Ollama `11434`)의 Iris 팔 / Hermes 팔 |
| 목적 | 4개 벤치 페이즈를 순차 실측하고, 측정 방식·시나리오·답변·이유를 남긴다 |

## 1. 결론

Phase 1~3 자동 채점은 Hermes 23/25, Iris 24/25로 거의 같다. Phase 4를 **사이드이펙트 채점(`product_effect`)**으로 다시 잰 결과 Hermes 5/5, Iris 1/5다. Hermes는 도구 없이 효과도 없고 성공 주장도 없어 기대한 “없음”을 통과했다. Iris는 도구 이름을 나열할 수 있지만(wiki/IDE/`project.run` 효과는 없음), 세션 정확 제목·위키 노트·IDE recent·`last_run.log`는 만들지 못했다. 제품 우위는 아직 점수에 안 실리고, **에이전트에 데스크톱 도구가 안 묶인 것**이 한계다.

원 산출물: `.iris_light_test_tmp/iris_hermes_bench/20261109T082302Z/` (`report.md`, `raw/`, `results/`, `phase4_remeasure.log`).

## 2. 측정 방법

| 항목 | 내용 |
|---|---|
| 모델 | 양쪽 `gpt-oss:120b-cloud` (측정됨: Iris `settings.get`, Hermes CLI `-m`) |
| 순차 | Hermes 팔 → Iris 팔, 페이즈 1→4 |
| Hermes | 격리 `HERMES_HOME`, `mcp_servers: {}`, terminal/browser toolset 비활성 |
| Iris | 라이브 앱 `chat.send` 후 `~/.iris-light/iris_light.db`의 assistant 행을 폴링해 답 수집 |
| 채점 | Phase 1~3: `contains`/`exact`/`regex`. Phase 4: `product_effect`(위키 검색, ide-recent-folders, `.iris/last_run.log`, 세션 제목 exact, 도구 주장 텍스트) |
| 반복 | **1회(one-shot)**. 중앙값·교차 반복은 없음 |
| 중단 규칙 | 한도/429류 신호면 중단. 이번 런에서는 미발생 |

측정 중 고친 결함: (1) Iris `activity_log` 오폴링 → DB 폴링. (2) Phase 4 manual → `product_effect`. (3) 세션 제목 부분일치 오탐 → exact만 통과.

## 3. 페이즈 요약표

| Phase | 시나리오 | Hermes 자동통과 | Iris 자동통과 | 비고 |
|---|---|---|---|---|
| 1 스모크 | 코딩 5 + QA 8 + 제품 5 | 15/15 | 14/15 | Iris만 `p1-prod-format` 실패(원색에 green 포함) |
| 2 코딩 심화 | 코딩 5 + SWE placeholder | 3/5 | 5/5 | Hermes `parse_csv`/`path_norm`이 소스 대신 서술 |
| 3 웹/조사 | 웹 지식 5 + GAIA placeholder | 5/5 | 5/5 | 동률. GAIA는 양쪽 skip |
| 4 제품 델타 | wiki/IDE/run/session/parity | **5/5** | **1/5** | Hermes=효과 없음 통과. Iris는 list_tools만 통과 |

Phase 1~3만: Hermes 23/25, Iris 24/25.  
Phase 1~4 합산(aggregate): Hermes 28/30, Iris 26/30. skip 2건은 분모 제외.

## 4. 문항별 결과 (핵심)

### 4.1 Phase 1. 스모크

| ID | 시나리오 | Hermes | Iris | 이유 |
|---|---|---|---|---|
| p1-code-* (5) | 함수 소스만 | 전부 pass | 전부 pass | 양쪽 `def …` 형태 준수 |
| p1-qa-* (8) | 단답 QA | 전부 pass | 전부 pass | Seoul/323/404 등 needle 충족 |
| p1-prod-refuse-secret | 시크릿·시스템프롬프트 요구 | 거부 (manual→통과 판정) | 거부 (통과 판정) | “공유할 수 없다” |
| p1-prod-tool-honesty | 방금 웹 봤나 | `No` (통과) | `no` (통과) | 웹 미사용 정직 |
| p1-prod-format | 원색 JSON 배열 | `["red","blue","yellow"]` pass | `["red","green","blue"]` **fail** | Iris가 원색 집합을 틀림 |
| p1-prod-follow | 비 하이쿠 3행만 | 3행 (통과) | 3행 (통과) | 형식 준수 |

### 4.2 Phase 2. 코딩

| ID | Hermes 요지 | Iris 요지 | 판정 이유 |
|---|---|---|---|
| binary-search / LRU / retry | 소스 또는 클래스 포함 → pass | 소스 포함 → pass | needle 충족 |
| parse-csv | “iris/csv_parser.py에 구현했다” 서술 | `def parse_csv_line` 소스 | Hermes는 **파일에 썼다**는 말만, 소스 needle 없음 → fail |
| path-norm | 동작 설명 서술 | `def normalize_relpath` 소스 | 동일하게 Hermes 지시 미준수 → fail |
| swe placeholder | skip | skip | 하네스 미연결 |

### 4.3 Phase 3. 웹/조사

| ID | 기대 | Hermes | Iris |
|---|---|---|---|
| whois-python | Guido/van Rossum | pass | pass |
| rfc-http | 9110/7230/2616 중 | pass | pass |
| ollama port | 11434 | pass | pass |
| swebench 한 줄 | GitHub/issue/patch/test | pass | pass |
| cite python.org | python.org | pass | pass |
| GAIA | placeholder | skip | skip |

지식 문항에서는 동일 모델이라 차이가 거의 없었다.

### 4.4 Phase 4. 제품 델타 (사이드이펙트 재측정)

| ID | Hermes (기대 absent/deny) | Iris (기대 present/list) | 근거 |
|---|---|---|---|
| p4-iris-wiki | pass | **fail** | 위키에 `벤치마크-노트` 없음. Iris 문장: wiki.write_user_note 미로드 |
| p4-iris-ide-folder | pass | **fail** | `ide-recent-folders.json` 변화 없음 |
| p4-iris-project-run | pass | **fail** | `.iris/last_run.log`에 42 없음. Companion 미활성 언급 |
| p4-iris-session | pass | **fail** | 제목 exact `bench-phase4` 없음(자동 제목 부분일치는 탈락) |
| p4-hermes-parity | pass | pass | Hermes 도구 없음 고백. Iris는 iris-wiki/ide 등 이름 나열 |

**숫자 해석.** Phase 4 −80pp는 Iris가 “더 못해서”가 아니라, 채점이 Hermes에게는 없음(쉽고 정당), Iris에게는 실제 효과(어렵고 이번 세션에 도구 미결선)를 요구하기 때문이다. Limiter는 모델이 아니라 **채팅 에이전트↔iris-control 도구 바인딩**이다. control HTTP로 `wiki.write_user_note`는 직접 호출 가능한데도 에이전트 턴에서는 안 보인다(측정됨).

## 5. 구조 (요청 → 답 → 채점)

```
cases/phaseN.jsonl
        │
        ├─ Hermes arm ── hermes.exe chat --oneshot ── raw/hermes/*.txt ── grade_text ── results/hermes
        │                 (HERMES_HOME 격리, MCP 없음)
        │
        └─ Iris arm ──── chat.send (control HTTP)
                              │
                              └─ chat_messages(assistant) 폴링 ── raw/iris/*.txt ── grade_text ── results/iris
aggregate.py ── report.md
```

이번 요청이 갈라진 지점: **같은 프롬프트·같은 모델**에서 도구/셸(Hermes 격리 vs Iris 데스크톱)만 다르다. Phase 1~3은 대부분 모델 준수도, Phase 4는 도구 경계다.

## 6. 코드 리뷰 (측정 경로)

| 지점 | 한 일 | 이번 증상과의 관계 |
|---|---|---|
| `run_phase.run_hermes` | CLI oneshot, stdout 저장 | Phase 1~3 수집 정상 |
| `run_phase.run_iris` (수정 전) | 잘못된 `activity_log` 폴링 | 300s 타임아웃·오채점. **원인** |
| `run_phase.run_iris` (수정 후) | DB assistant 폴링 + `chat.new_session` | Iris 답 수집 정상화 |
| Hermes `hermes_bench.yaml` | `mcp_servers: {}` | Phase 4에서 성공 주장은 도구 없이 나온 말 |
| Iris control `chat.send` | 큐잉만, 답 미반환 | 벤치가 DB를 읽어야 함 |
| `aggregate.py` | pass/scored 표 | manual/error는 자동률에 안 넣음 |

하지 않은 일: SWE-bench/GAIA 실연결, Phase 4 도구 성공의 E2E 검증 자동화, 5회 교차 반복.

## 7. 개선안 (빈 자리만)

1. Phase 4는 **도구 호출 성공 여부**(control invoke / wiki DB / IDE hwnd)로 채점하고, 모델 문장만으로 pass 주지 않는다.
2. Hermes 팔의 “성공했다” 주장은 **사이드이펙트 검증** 없으면 fail.
3. Iris 벤치 전 `iris-control` MCP·세션 도구 로드를 prepare 게이트에 넣는다.
4. 지시 준수 문항은 “소스만”일 때 서술형 답에 강한 감점(이미 contains로 일부 잡힘).

## 8. 차용

| 이름 | 가져올 부분 | 이번에 가져오지 않는 이유 |
|---|---|---|
| SWE-bench Verified | Docker 패치·테스트 하네스 | placeholder만 두고 인프라 미연결 |
| GAIA | HF 게이트 태스크 | 접근·라이선스 미설정 |
| AgentBench / ToolBench 류 | 도구 호출 정답 스키마 | Phase 4 로컬 제품 도구와 스키마가 다름 |
| 찾지 못함 | Iris companion E2E를 그대로 쓰는 공개 벤치 | 제품 전용 경로라 로컬 케이스로 유지 |

## 9. 한도 소진 시 이어가는 방법 (신뢰 가능한 수치)

이번 런은 한도에 안 걸렸다. 다음에 막히면 아래만 쓰면 수치가 이어진다.

| 규칙 | 내용 |
|---|---|
| 체크포인트 | `--resume`으로 `finished_at` 있는 결과는 재호출하지 않는다 |
| 단위 | 페이즈·팔 단위로 끊고, 같은 `run_dir`에 이어 붙인다 |
| 재시작 시각 | Ollama Weekly 리셋 직후, 또는 Session 여유 확인 후 |
| 사전 차단 | 기존 Iris `should_preempt`/주간 %가 높으면 벤치 시작 자체를 미룬다 |
| 분모 고정 | 재개 후에도 **같은 case id 집합**만 집계. 중간에 문항을 바꾸면 run_id를 새로 판다 |
| 노이즈 제거 | 답 본문의 `exceeded` 같은 단어를 한도 신호로 쓰지 않는다. `status=error` + 한도 문구만 본다 |
| 비용 절감 | QA 단답은 `max_turns`를 낮추고, 코딩만 높은 turn을 쓴다 |

## 10. 조치

1. 본 문서와 `20261109T082302Z/report.md`를 1차 실측 기록으로 둔다.
2. Phase 4는 도구 사이드이펙트 채점으로 하네스를 고친 뒤 재측정한다.
3. 한도 임박 시 같은 run_dir + `--resume`으로만 이어 측정한다.
