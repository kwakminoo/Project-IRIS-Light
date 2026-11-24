# NamePlan arena — cross-judge

| 항목 | 내용 |
|---|---|
| 역할 | arena cross-judge (Composer 계열 아님) |
| 기준 | 6항목, 각 1–5, 동일 가중 |
| 판독 | candidate-1 DESIGN, candidate-2 DESIGN, GROUNDING, 현행 `plan_local_file_writes` / `default_generated_rel_path` 호출 |

## 판정

**베이스는 Candidate 1.** 합계 23 대 21.

한 함수(`resolve_create_rel_path`)로 vibe와 Verify가 이름을 나누고, `default_generated_rel_path`는 C에서 호출을 옮긴 뒤 지운다. `LocalWritePlan` / `VerifyResult`는 유지해서 `turn_verify`와 `main_window`의 `kind == "ask"` 분기가 한 번에 깨지지 않는다.

Candidate 2의 목적지 불변과 “무이름이면 ask 하지 않음”만 가져온다. `WriteBatch`로 계획을 갈아엎는 안은 베이스가 아니다.

## 점수

| # | 기준 | C1 | C2 |
|---|---|---:|---:|
| 1 | vibe + Verify 단일 명명 권한 (`default_generated` 없음) | 4 | 4 |
| 2 | 무이름 생성은 영어 경로로 즉시 기록 (이름 질문 없음) | 3 | 4 |
| 3 | 이전 후 삭제, `iris_generated` 발명 금지, 이중 작성자 없음 | 4 | 3 |
| 4 | 공개면이 작고 호출부는 얇다 | 4 | 3 |
| 5 | C→A→B가 깨끗하고, 임시 호환을 남기지 않는다 | 4 | 3 |
| 6 | 동작으로 검증한다 (구현 트집 아님) | 4 | 4 |
| | **합계** | **23** | **21** |

## 1. 단일 권한 — 4 / 4

둘 다 정책을 `default_generated_rel_path`에서 빼서 한 모듈로 모은다. vibe 세 곳(`_live_vibe_open_target`, `_write_fenced_once`, `_try_reveal_local_vibe_code`)과 Verify가 그 모듈을 부른다.

감점 공통: GROUNDING은 공유 resolve의 집을 `iris/ui/chat/file_write_claim.py`로 고정했다. 둘 다 새 `name_plan.py`를 권한으로 둔다. vibe는 `file_write_claim`을 부르지 않는다.

Candidate 1 추가 감점: 이름이 이미 있으면 `plan_local_file_writes`가 `named_rel_paths`를 그대로 zip 하고 `resolve_create_rel_path`를 타지 않는다. `RelPath` 금지가 그 경로에는 없다. open은 `assistant=""`인데 plan은 assistant와 code를 넘긴다. “같은 함수”여도 입력이 달라 파일이 둘일 수 있다.

Candidate 2 추가 감점: 공개 진입이 `destinations_for_create_turn`과 `write_batch_for_create_turn` 둘이다. 일치는 주석이다. 초입은 빈 펜스, 턴 끝은 본문이 있는 펜스라, code 힌트를 쓰면 경로가 갈라진다. `RelPath = NewType`은 생성 시 `iris_generated`를 막지 못한다.

## 2. 즉시 영어 경로 — 3 / 4

Candidate 1의 한 펜스 경로는 맞다. 한국어 목표 → 구문표 또는 로마자 → `gugudan.py` / `script` 폴백. LLM 없음. 「파일 이름을 알려 주세요」는 한 펜스에서 빠진다.

감점: 이름 0개이고 펜스가 2개 이상이면 여전히 ask다. 문구는 개수 불일치 문장이다. 이름을 안 준 생성에 대한 ask를 남긴 것이다. “grounding이 개수 불일치 ask를 허용”이라고 적은 문장은 GROUNDING에 없다. 그 문서는 무이름 생성의 규칙 ask를 지우라고 한다.

Candidate 2는 ask 변형이 없다. 한 펜스 무이름은 `invent_english_rel`로 바로 쓴다. 감점: 무이름 다중 펜스는 `()` skip이라 즉시 기록이 아니다. 영어 stem 규칙은 TODO다. 이름 있는 N≠M까지 skip하면, 오늘 `kind=="ask"`로 만족시키던 `needs_recovery`가 failover/stop으로 바뀐다. 그 부작용은 설계에 없다.

## 3. 이전 후 삭제 — 4 / 3

Candidate 1 단계 C: 세 호출을 옮기고 `default_generated_rel_path`와 `iris_generated.py` self-check를 지운다. 같은 단계에서 plan의 한 펜스 무이름도 resolve로 붙여, C와 B 사이에 “vibe는 영어 파일, Verify는 ask”가 남지 않게 한다. 시임 함수는 없다.

감점: 명시 이름 zip이 resolve 밖의 두 번째 경로다. `named_rel_paths`는 `iris_generated.py`만 거르므로 `iris_generated.js`는 zip으로 통과할 수 있다.

Candidate 2 단계 C는 helper 삭제 순서는 맞다. 그러나 B 전까지 Verify ask가 살아 있어 명명 정책이 둘이다. `plan_local_file_writes → WriteBatch` 시임은 반환 타입이 오늘 `LocalWritePlan`과 다르다. `turn_verify.py`의 `planned.kind`, `main_window`의 `plan.kind == "ask"`, `_check_turn_verify`의 `pairs[0]`이 즉시 깨진다. 호환 계층이 아니다. `named_rel_paths`를 claim에 둘지 name_plan으로 옮길지도 “or”로 남아 있다.

## 4. 공개면 — 4 / 3

Candidate 1 호출부는 `resolve_create_rel_path` 하나만 새로 안다. Verify는 기존 `plan_local_file_writes`를 유지한다. 로마자, 구문표, 금지어, 접미사는 모듈 안에 있다. 초입 open은 펜스가 닫히기 전에도 이 함수만으로 된다. 오늘 `extract_all_code_blocks`는 닫힌 펜스만 보므로, 이 분리가 맞다.

감점: plan 본문이 ask/skip/write를 다시 가른다. `infer_english_stem` / `lang_suffix`가 private로 적혀 있지 않다.

Candidate 2는 깊은 모듈을 말하지만 공개로 `make_rel_path`, `invent_english_rel`, `resolve_destinations`, destination/batch 함수, `FenceBody`, `WriteSlot`, `WriteBatch`, `BannedGeneratedName`을 꺼낸다. `VerifyResult.local_plan`을 `local_batch`로 바꿔 호출부 전부가 새 타입을 배운다. 거절한 대안 1(기존 plan에 invent만 넣기)이 호출부는 더 얇다.

## 5. 단계 — 4 / 3

순서는 둘 다 C → A → B다. A는 nudge 문장과 버전 올림뿐이라 맞다.

Candidate 1은 C에 plan 동작 변경을 끌어온다. 기존 `_check_file_write_claim`은 「스크립트 만들어줘」+ 펜스 1개를 ask로 고정하므로, 테스트 갱신을 B까지 미루면 C는 붉다. 영구 시임은 없다. 이중 작성자를 피하려는 겹침이라 4.

Candidate 2의 C/B 표는 역할이 더 깨끗해 보인다. C 완료 조건 “같은 goal이면 vibe 경로 == verify 경로”는 B 전에는 거짓이다. 무이름이면 verify가 아직 ask다. 시임 삭제가 어느 단계 완료 조건에도 없다.

## 6. 검증 가능성 — 4 / 4

Candidate 1: 무이름 → write, ask 문장 소거, vibe 경로 == plan 경로, `구구단` → `gugudan.py`. 동작 단언이 있다. 감점: 완료 조건에 `rg default_generated_rel_path`와 “open이 이 함수를 호출”이 있다. 호출 여부는 동작이 아니다.

Candidate 2: 오늘 테스트와 같은 「스크립트 만들어줘」+ 펜스 1개가 영어 파일을 쓰고 ask가 없어야 한다. vibe와 batch 경로 일치. 감점: “영어 파일”만으로는 `script.py`도 통과한다. C 완료 조건의 “참조가 없다”는 구현 단언이다.

## 차용 (Candidate 2에서 2개)

1. **무이름 다중 펜스는 ask 하지 않는다.** 이름 0개 + 펜스 ≠ 1 은 빈 결과(skip)다. 개수 불일치 문구로 바꾸지 않는다. 사용자가 이름을 줬는데 N≠M인 ask는 Candidate 1대로 둔다. `VerifyAction`의 ask 제거, `WriteBatch` 교체는 가져오지 않는다.
2. **한 번 정한 경로는 턴 안에서 다시 추론하지 않는다.** open이 쓴 `RelPath`가 있으면 Verify의 그 펜스는 그 경로에만 쓴다. stem 입력은 goal, lang, 명시적 이름뿐이다. 나중에 보이는 펜스 본문으로 파일을 새로 만들지 않는다. 코드 힌트는 open이 없을 때의 단일 추론에만 쓴다.

## 가져오지 않는 것

- `LocalWritePlan` 삭제와 `plan_local_file_writes → WriteBatch` 시임
- `RelPath = NewType` (검증은 Candidate 1의 `RelPath.parse`)
- 이름 있는 개수 불일치까지 skip
- 공개 함수를 destination/batch 둘로 늘리는 것

## 베이스에 묶는 수정

`resolve_create_rel_path`의 집은 `iris/ui/chat/file_write_claim.py`다. vibe와 `plan_local_file_writes`가 그 함수만 부른다. 파일이 비대해 보조 모듈이 필요하면 구현만 옮기고, 공개 진입은 claim에 둔다. 명시 이름도 `RelPath.parse`를 통과한 뒤 pair가 된다.
