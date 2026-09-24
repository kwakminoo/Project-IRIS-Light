# Core「연결 검증」gateway_ready 실패 — 원인 분석 · 개선안

> **작성**: 2026-09-25  
> **재현**: START PROTOCOL Core 9/10「Core 연결 검증」실패  
> **UI**: `[HEALTH] /health OK 이지만 gateway_ready 실패 (API 키 또는 /v1/models).`  
> **부수 문구**: `Ollama 클라우드 로그인: 안 됨` (사용자는 앱에서 이미 로그인)  
> **진단 JSON**: `code=OK`, `message=gateway 이미 실행 중`, `/health` ok, `has_api_key=true`  
> **관련**:  
> - `Hermes채팅401-ctx미달-프로토콜보강-검토와-프롬프트.md` (게이트웨이 키·already-running)  
> - `Hermes채팅401-클라우드미로그인-원인과-개선안.md` (채팅 SSE 401 = Ollama cloud — **이번 Core 실패와 별개**)  
> - Setup packages Access Denied (연번 23) — **이번과 무관, 이미 수정됨**

---

## 1. 한줄 결론

| # | 판정 | 내용 |
|---|------|------|
| A | **확정 버그** | `hermes_gateway` 스텝은 `/health`만 보고 「이미 실행 중 → done」인데, `core_smoke`/`verify_core`는 `gateway_ready`(`/health`+키+`/v1/models`)로 **더 엄격히** 판정 → 앞은 ✓ 뒤는 ✗ |
| B | **확정 UX 오진** | 실패 메시지에 붙는 `Ollama 클라우드 로그인: 안 됨`은 **이번 실패 원인이 아님**. 로컬 `gemma4:e2b`가 있어 Core `usable`은 이미 통과 |
| C | **유력** | 진단의 `has_api_key=true`는 **디스크 `.env`에 키가 있다**는 뜻이지, 떠 있는 gateway 프로세스가 그 키로 `/v1/models`를 받아준다는 뜻이 **아님** |
| D | **재시도 no-op** | 「재시도」는 같은 `verify_core`만 다시 돌림. gateway_ready 실패는 401/`[API_KEY]` 복구(키 rotate+restart) 분기에 **안 걸림** |

**한줄:** 게이트웨이 **생존(/health)** 과 **채팅 준비(gateway_ready)** 계약이 Core 안에서 갈라져 있고, 클라우드 로그인 문구가 원인을 가린다.

---

## 2. 사용자 스냅샷과의 정합

| 관측 | 의미 |
|------|------|
| Hermes 설치~gateway 기동 ✓ | `_step_hermes_gateway` 가 `timeout_sec=2.0` → **health만** 통과 후 `mark_gateway_already_running` |
| 진단 JSON `gateway 이미 실행 중` + health ok + has_api_key | `mark_gateway_already_running` 출력과 **완전 일치** (`/models` 미검사) |
| Core 연결 검증 ✗ + gateway_ready 문구 | `verify_core` → `is_hermes_gateway_running` (**timeout 없음**) → `gateway_ready()` 실패 |
| 로컬 모델 `gemma4:e2b` 있음 | `inspect_inference.usable=True` — 추론 백엔드 부족으로 막힌 게 **아님** |
| 클라우드 로그인 「안 됨」 | `format_inference_report`가 **항상** 붙이는 상태줄. 앱 UI 로그인과 `/api/me` 판정이 어긋날 수 있음 |

---

## 3. 코드 계약 (문제의 핵심)

```text
_step_hermes_gateway
  already = is_hermes_gateway_running(url, api_key, timeout_sec=2.0)
       → HermesClient.health_ok()          # /health 만
  → mark_gateway_already_running()         # 진단 OK + has_api_key=.env 존재
  → step done ✓

_step_core_smoke → verify_core
  is_hermes_gateway_running(url, api_key)  # timeout 없음
       → HermesClient.gateway_ready()
            /health + api_key 비어있지 않음 + GET /v1/models
  → 실패 시 health OK 이면 지금 UI 문구
```

| 함수 | timeout_sec | 실제 검사 |
|------|-------------|-----------|
| `is_hermes_gateway_running(..., timeout_sec=2)` | 있음 | `/health`만 |
| `is_hermes_gateway_running(...)` | 없음 | `gateway_ready` |
| `mark_gateway_already_running` | — | health + `.env` 키 **존재** |
| `gateway_ready` | — | health + 키 + `/v1/models` (예외 **삼킴**) |

이전 문서(401·ctx)에서 이미 지적한 **「이미 실행 중이면 재기동 안 함 → 옛 키」** 와 같은 축이다.  
그때는 채팅 401로 드러났고, **지금은 Core smoke가 gateway_ready에서 먼저 막히는 형태**.

---

## 4. 원인 후보 표

| 연번 | 가설 | 근거 | 신뢰도 |
|------|------|------|--------|
| H1 | **health vs gateway_ready 이중 계약** | gateway ✓ / smoke ✗ + 진단 JSON이 mark_* 경로 | **확정** |
| H2 | 프로세스 메모리 키 ≠ `.env` / Iris 키 | already-running 유지 + hermes_env가 키를 바꿨을 수 있음; `/models` 401 → gateway_ready False | **높음** |
| H3 | `/v1/models` 예외 삼킴으로 원인 불명 | `gateway_ready` `except: return False` — UI가 「API 키 또는 /v1/models」로만 뭉뚱그림 | **확정(관측)** |
| H4 | 클라우드 「안 됨」이 실패 원인처럼 보임 | report 항상 첨부; 로컬 모델 있으면 Core에 로그인 불필요 | **확정(오진)** |
| H5 | 앱 로그인 ≠ `POST :11434/api/me` + `email` | `ollama_cloud_signed_in` 구현; UI만 로그인된 경우 false negative | **중간~높음** |
| H6 | 「재시도」가 gateway_ready 실패에 복구 없음 | `_step_core_smoke` 복구는 `[API_KEY]`/401(클라우드 제외)만 | **확정** |
| H7 | `/models` 일시 타임아웃·기동 직후 레이스 | health 먼저 살아나고 models 지연 가능 | **중간** |

---

## 5. 클라우드 로그인 문구 — 왜 앱과 다른가

```python
# ollama_usage._ollama_signed_in
POST http://127.0.0.1:11434/api/me  →  JSON에 email 있으면 True
```

| 상황 | 결과 |
|------|------|
| Ollama **앱 UI**에 계정 표시 | Iris와 무관할 수 있음 |
| 데몬 `/api/me` 실패·email 없음·필드 변경 | Iris = 「안 됨」 |
| 로컬 모델만 쓰는 Core | 로그인 **불필요**인데도 report에 「안 됨」이 붙음 |

이번 실패 경로에는 `[CLOUD]` 태그가 **없다** (클라우드 가드 분기가 아님).  
즉 **로그인해서 고칠 문제가 아닌데**, 안내가 로그인으로 유도한다.

채팅 `Hermes: HTTP 401: Unauthorized`(클라우드 모델) 문서와 **혼동 금지**.

---

## 6. 이전 기록과의 대조

| 문서 / 연번 | 증상 | 이번과의 관계 |
|-------------|------|----------------|
| 401-ctx 보강 | 약한 키·already-running → **채팅** 401 | **같은 already-running 구멍**. 지금은 smoke가 gateway_ready로 조기 실패 |
| 401-클라우드미로그인 | 채팅 SSE 401 + `*:cloud` | Core 문구의 「안 됨」과 **무관**. 로컬 gemma4:e2b면 그 경로 아님 |
| Hermes 설치 실패 (22) | Core 4 Hermes pip | 이번은 Core 9, Hermes 설치 ✓ |
| Setup packages (23) | Inno setup.ps1 Access Denied | 사용자 말대로 Setup은 고쳐짐. **별건** |

**다시 쓰지 말 것:**  
- 이 증상에 Setup `-Recreate` / Access Denied 패치  
- 「클라우드 로그인만 하면 Core smoke 통과」로 단정  
- gateway_ready 실패에 **무조건** API 키 rotate만 (원인 로그 없이)

---

## 7. 개선안

| 연번 | 구분 | 사항 | 위치 | 등급 | 권장 |
|:---:|------|------|------|------|------|
| 1 | 계약 | `hermes_gateway` already 판정도 **gateway_ready**(또는 `probe_chat_auth`)까지 | `setup_protocol._step_hermes_gateway` | **긴급** | `timeout_sec=2` health-only로 done 주지 말 것. health만이면 「기동됨·채팅 미검증」으로 두거나 바로 models/auth probe |
| 2 | 관측 | `gateway_ready` 실패 시 HTTP 코드·본문 꼬리·키 weak 여부·키 길이만 메시지에 | `hermes_client.gateway_ready` → `probe_gateway_ready()` 결과형 | **긴급** | 「API 키 또는 /v1/models」 뭉뚱그림 제거 |
| 3 | 복구 | core_smoke: health OK + models/auth 실패 → **키 정합 검사 후 1회 force restart** (이미 401 분기와 합치기) | `_step_core_smoke` | **중요** | 재시도가 no-op이 되지 않게 |
| 4 | UX | 실패 detail에 report 붙일 때: gateway 실패면 클라우드 줄을 **부록/축소**하거나 「로컬 모델 있음 — 로그인 불필요」명시 | `verify_core` / `format_inference_report` | **중요** | 오진 제거 |
| 5 | 로그인 감지 | `/api/me` 외 폴백(응답 스키마·쿠키·문서화된 엔드포인트) + false negative 시 문구 「앱 로그인과 데몬 판정이 다를 수 있음」 | `ollama_usage.py` | 보통 | 앱 UI만 믿지 말 것 |
| 6 | 진단 JSON | `mark_gateway_already_running`에 `models_ok` / `chat_auth` 필드 추가 | `hermes_gateway.py` | 보통 | 복사 진단이 health와 ready를 구분 |
| 7 | 이름 | `is_hermes_gateway_running(timeout_sec=…)` → `health_ok` / `ready` 명시 분리 | gateway 모듈 | 보통 | 이중 의미 제거 |
| 8 | 테스트 | health OK·models 401 mock → gateway step이 done이 되면 안 됨; smoke 메시지가 클라우드를 원인처럼 안 쓰게 | unittest | **중요** | 회귀 방지 |

### 우선 구현 순서

1. 연번 1 + 2 + 6 (계약 정렬 + 원인 보이게)  
2. 연번 3 + 4 (재시도 복구 + UX)  
3. 연번 5 + 7 + 8

### 부적합

- Core에 긴 클라우드 추론 smoke  
- 로컬 모델 있는데 클라우드 로그인을 Core 필수로 승격  
- Setup.exe / venv Access Denied 경로 재손대기  
- Hermes 업스트림 포크만으로 `/models` 고치기

---

## 8. 지금 사용자 PC에서 할 일 (코드 배포 전)

1. Iris·관련 터미널을 끄고, 작업 관리자에서 `gateway run` / 8642 리스너 정리.  
2. `%LOCALAPPDATA%\hermes\.env` 의 `API_SERVER_KEY`와 프로젝트 `.env` `IRIS_HERMES_API_KEY`가 **같은지** 확인 (길이가 짧거나 `change-me`면 약함).  
3. 시작 프로토콜 **다시 설정**(재시도만 말고) — 배포 후에는 gateway_ready 실패 시 자동 restart가 들어가야 함.  
4. 클라우드 로그인 문구는 **무시**해도 됨 (로컬 `gemma4:e2b` 있음). 채팅에서 `*:cloud` 모델을 쓸 때만 앱·데몬 로그인 정합이 필요.

수동 확인 (PowerShell):

```powershell
# /health (키 불필요)
Invoke-RestMethod http://127.0.0.1:8642/health
# /v1/models (Bearer = hermes .env API_SERVER_KEY)
$key = (Get-Content "$env:LOCALAPPDATA\hermes\.env" | ? { $_ -match '^API_SERVER_KEY=' }) -replace '^API_SERVER_KEY=',''
Invoke-RestMethod http://127.0.0.1:8642/v1/models -Headers @{ Authorization = "Bearer $key" }
```

`/models`가 401이면 → 키 불일치(H2).  
200이면 → Iris 쪽 base_url/키 resolve 경로를 의심(배포 후 연번 2로 잡힘).

---

## 9. 상태

| 항목 | 상태 |
|------|------|
| 원인 범위 조사 | **완료** (본 문서) |
| 코드 수정 | **완료** (2026-09-25) — probe_gateway_ready · gateway 스텝 ready 계약 · smoke restart · report 오진 완화 · Setup 0.1.15 |
| 총괄표 | 연번 **24** 완료 |

---

## 10. 이력

| 날짜 | 내용 |
|------|------|
| 2026-09-25 | Core 9 gateway_ready UI + 진단 JSON 대조. H1 이중 계약·H4 클라우드 오진 확정. 이전 401 already-running 이슈와 동일 축으로 정리. |
| 2026-09-25 | 구현: `GatewayReadyResult`, hermes_gateway already=ready 필수, smoke `[READY]` 1회 restart, format_inference_report gateway_failure, `/api/me` 스키마 폴백. unittest 통과. Setup 0.1.15. |
