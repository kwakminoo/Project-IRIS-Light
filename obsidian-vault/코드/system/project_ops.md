# project_ops

`iris/system/project_ops.py`

프로젝트 폴더 찾기·스캐폴드·파일 쓰기 (Iris Control용).

## 주요 정의

- `def default_project_parents`
- `def resolve_project_parents`
- `def _norm_name`
- `def find_similar_projects`
- `def pick_similar_project`
- `def best_similar_project`
- `def create_scaffold`
- `def resolve_under_root`
- `def write_project_file`
- `def is_code_reveal_request`
- `def is_run_request`
- `def extract_first_code_block`
- `def default_generated_rel_path`
- `def write_project_file_stream`
- `def _smooth_text_chunks`
- `def build_iris_terminal_command`
- `def upsert_iris_run_task`
- `def wait_for_run_log`
- `def result_from_terminal_log`
- `def iris_run_log_path`
- `def build_run_command`
- `def run_project_command`
- `def format_run_log`
- `def summarize_run`

## 내부 의존성

- [[win_subprocess]]
