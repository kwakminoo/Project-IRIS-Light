# Iris vs Hermes capability bench

같은 모델로 Iris / Hermes를 **순차** 비교한다. 기본 모델은 `gpt-oss:120b-cloud` (Ollama `11434`).

## 준비 (벤치 전)

```powershell
cd <repo>
.\.venv\Scripts\python.exe scripts\iris_hermes_bench\prepare.py
```

`ready: true` 와 `run_dir` 경로를 확인한다. 산출물은 `.iris_light_test_tmp/iris_hermes_bench/<run_id>/`.

Hermes 팔은 그 안의 `hermes_home/` (iris-control MCP 없음)만 쓴다. 사용자 `config.yaml`은 건드리지 않는다.

## Dry-run (LLM 호출 없음)

```powershell
.\.venv\Scripts\python.exe scripts\iris_hermes_bench\run_phase.py --run-dir <run_dir> --phase 1 --arm both
# phase 2,3,4 반복
.\.venv\Scripts\python.exe scripts\iris_hermes_bench\aggregate.py --run-dir <run_dir>
```

## 실제 실행 (순차)

Hermes 팔 → Iris 팔 순. 한 페이즈씩.

```powershell
.\.venv\Scripts\python.exe scripts\iris_hermes_bench\run_phase.py --run-dir <run_dir> --phase 1 --arm hermes --execute
.\.venv\Scripts\python.exe scripts\iris_hermes_bench\run_phase.py --run-dir <run_dir> --phase 1 --arm iris --execute
# … phase 2,3,4
.\.venv\Scripts\python.exe scripts\iris_hermes_bench\aggregate.py --run-dir <run_dir>
```

마지막에 `report.md` 비교표를 본다. `manual` 행은 사람이 `results/*/…json` 의 `ok`/`status`를 고친 뒤 aggregate를 다시 돌린다.

## 페이즈

| Phase | 내용 |
|---|---|
| 1 | 스모크 코딩·QA·제품 |
| 2 | 코딩 심화 (+ SWE placeholder skip) |
| 3 | 웹/조사 (+ GAIA placeholder skip) |
| 4 | Iris 제품 델타 (위키/IDE/control) |

모델 변경은 `manifest.defaults.json` 의 `model` 만 바꾼 뒤 prepare를 다시 한다.
