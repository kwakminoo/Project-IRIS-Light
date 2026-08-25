# setup_protocol

`iris/system/setup_protocol.py`

Iris 첫 실행 시작 프로토콜 — Detect / Provision / Wire / Start / Verify.

## 주요 정의

- `def is_setup_demo`
- `def is_setup_dry_run`
- `def is_setup_preview`
- `def setup_state_path`
- `def prepare_setup_demo`
- `def prepare_setup_dry_run`
- `class SetupStepResult`
- `def parse_install_percent`
- `def _decode_frame`
- `def _split_off_frame`
- `def _utc_now`
- `def _default_state`
- `def load_setup_state`
- `def save_setup_state`
- `def is_core_ready`
- `def mark_core_ready_if_healthy`
- `def reset_core_ready`
- `def default_min_model`
- `def _iris_env_path`
- `def _upsert_dotenv`
- `def _winget_exe`
- `def _winget_available`
- `def _kill_proc_tree`
- `class SetupProtocol`
- `def _list_ollama_model_names`
- `def _self_check`

## 내부 의존성

- [[aloha_runtime]]
- [[android_emulator]]
- [[hermes_gateway]]
- [[hermes_iris_control_sync]]
- [[ollama_client]]
- [[ollama_server]]
