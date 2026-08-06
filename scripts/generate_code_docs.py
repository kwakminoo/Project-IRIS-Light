"""iris/ 소스코드를 obsidian-vault 아래 실제 .md 노트로 구워낸다.

이렇게 만든 노트는 IrisWiki의 기존 파이프라인을 그대로 타기 때문에, 별도 배선 없이도
좌측 문서 패널과 위키 그래프 구체 양쪽에 자동으로 나타난다. 실행할 때마다 대상 폴더를
비우고 다시 생성하므로, 삭제되거나 이름이 바뀐 소스 파일의 옛 노트가 남지 않는다.

사용법: .venv/bin/python scripts/generate_code_docs.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from iris.knowledge.code_index import CodeFile, IrisCodeIndex  # noqa: E402
from iris.knowledge.obsidian_vault import DEFAULT_VAULT_ROOT  # noqa: E402

OUT_DIR = DEFAULT_VAULT_ROOT / "코드"


def _render(cf: CodeFile, module_to_file: dict[str, CodeFile]) -> str:
    lines = [f"# {cf.title}", "", f"`iris/{cf.rel_path}`", "", cf.doc or "_설명 없음._"]

    if cf.symbols:
        lines += ["", "## 주요 정의", ""]
        lines += [f"- `{sym}`" for sym in cf.symbols]

    linked = sorted(
        {
            module_to_file[imp].title
            for imp in cf.imports
            if imp in module_to_file and module_to_file[imp] is not cf
        }
    )
    if linked:
        lines += ["", "## 내부 의존성", ""]
        lines += [f"- [[{title}]]" for title in linked]

    return "\n".join(lines) + "\n"


def main() -> int:
    files = IrisCodeIndex().list_files()
    module_to_file = {cf.module: cf for cf in files}

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)

    for cf in files:
        folder_dir = OUT_DIR / cf.folder
        folder_dir.mkdir(parents=True, exist_ok=True)
        (folder_dir / f"{cf.title}.md").write_text(_render(cf, module_to_file), encoding="utf-8")

    print(f"generated={len(files)} notes -> {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
