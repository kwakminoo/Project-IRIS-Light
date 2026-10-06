"""파일 쓰기 완료 문장 게이트와 사진→열린 파일 절차.

모델 계획 턴 없이, 쓰기는 project.write_file 결과와 디스크만 믿는다.
"""

from __future__ import annotations

import base64
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from iris.system.project_ops import extract_first_code_block

CHAT_ONLY = "채팅에만 있고 파일은 만들지 않았다"
_CODE_ONLY_PROMPT = "코드만 출력. 설명·파일명·완료 문장 금지"
_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
_WRITE_RE = re.compile(r"작성|넣어|써|스크립트|코드")
_CLAIM_RE = re.compile(r"처리 완료|생성하겠습니다|작성했습니다|파일을 열었습니다|저장했습니다")
_CODE_HINT = re.compile(
    r"(^\s*(import|from|def|class|for|while|if|return|print|const|let|var|function)\b)|[{}=();]",
    re.M,
)
_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}


@dataclass(frozen=True)
class GateResult:
    display: str
    suppress_followup_write: bool


def contains_completion_claim(text: str) -> bool:
    return bool(_CLAIM_RE.search(text or ""))


def verified_write_path(result: dict | None) -> str:
    if not isinstance(result, dict) or not result.get("ok"):
        return ""
    inner = result.get("result") if isinstance(result.get("result"), dict) else {}
    path = str(inner.get("path") or "")
    if path and Path(path).is_file():
        return str(Path(path).resolve())
    return ""


def reveal_line(path: str) -> str:
    p = (path or "").strip()
    if p and Path(p).is_file():
        resolved = Path(p).resolve()
        if resolved.suffix.lower() == ".pdf":
            return f"PDF로 저장했습니다.\n\n- 경로: `{resolved}`"
        return f"IDE에 `{resolved}` 파일을 열었습니다."
    return CHAT_ONLY


def settle_completion_claim(
    text: str,
    *,
    verified_path: str = "",
    try_write: Callable[[str, str], dict | None] | None = None,
) -> GateResult:
    """모델이 쓴 답을 그대로 둔다. 완료 단어로 파일을 쓰거나 문장을 바꾸지 않는다."""
    del verified_path, try_write
    return GateResult(text or "", False)


def image_write_request(text: str, attachments: list[str] | tuple[str, ...]) -> bool:
    if not _WRITE_RE.search(text or ""):
        return False
    return any(Path(p).suffix.lower() in _IMAGE_EXT for p in attachments)


def _image_path(attachments: list[str]) -> str:
    for raw in attachments:
        if Path(raw).suffix.lower() in _IMAGE_EXT:
            return raw
    return ""


def _editor_paths(editors: list[dict], project_root: str) -> list[Path]:
    root = Path(project_root).expanduser().resolve() if project_root else None
    if root is None or not root.is_dir():
        return []
    out: list[Path] = []
    seen: set[str] = set()
    for editor in editors:
        if not isinstance(editor, dict):
            continue
        raw = str(editor.get("path") or editor.get("uri") or "").strip()
        if raw.lower().startswith("file:"):
            from urllib.parse import unquote, urlparse

            raw = unquote(urlparse(raw).path)
            if raw.startswith("/") and len(raw) > 2 and raw[2] == ":":
                raw = raw[1:]
        if not raw:
            continue
        path = Path(raw)
        if not path.is_absolute():
            path = root / raw
        try:
            path = path.resolve()
        except OSError:
            continue
        if path != root and root not in path.parents:
            continue
        if path.is_dir():
            continue
        key = str(path).casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def prepare_image_code_pipe(
    text: str,
    attachments: list[str],
    *,
    project_root: str,
    workspace_root: str = "",
    search_roots: list[str] | None = None,
    list_editors: Callable[[], list[dict]],
    open_folder: Callable[[str], None] | None = None,
    open_file: Callable[[str], None] | None = None,
) -> dict:
    """passthrough | ask | ready. ready 전에는 write 를 호출하지 않는다."""
    if not image_write_request(text, attachments):
        return {"action": "passthrough"}
    from iris.ui.chat.at_path_refs import extract_at_path_refs, resolve_at_kind

    for ref in extract_at_path_refs(text):
        hit = resolve_at_kind(
            ref,
            workspace_root=workspace_root,
            project_root=project_root,
            search_roots=search_roots,
        )
        if hit["kind"] == "missing":
            return {"action": "passthrough"}
        if hit["kind"] == "folder" and open_folder is not None:
            open_folder(str(hit["path"]))
        elif hit["kind"] == "file" and open_file is not None:
            open_file(str(hit["path"]))
    editors = _editor_paths(list_editors() or [], project_root)
    if len(editors) != 1:
        return {"action": "passthrough"}
    root = Path(project_root).expanduser().resolve()
    rel = editors[0].relative_to(root).as_posix()
    return {"action": "ready", "rel": rel, "image": _image_path(list(attachments))}


def extracted_code(text: str) -> str:
    block = extract_first_code_block(text or "")
    if block and str(block.get("code") or "").strip():
        return str(block["code"])
    raw = (text or "").strip()
    if not raw or contains_completion_claim(raw):
        return ""
    if _CODE_HINT.search(raw):
        return raw
    return ""


def commit_extracted_code(
    text: str,
    *,
    rel: str,
    write_file: Callable[[str, str], dict],
) -> dict:
    code = extracted_code(text)
    if not code or not rel:
        return {"message": CHAT_ONLY, "wrote": False}
    try:
        result = write_file(rel, code)
    except Exception:
        result = None
    path = verified_write_path(result if isinstance(result, dict) else None)
    return {"message": reveal_line(path), "wrote": bool(path)}


def apply_image_code_pipe(
    text: str,
    attachments: list[str],
    *,
    project_root: str,
    workspace_root: str = "",
    search_roots: list[str] | None = None,
    list_editors: Callable[[], list[dict]],
    extract: Callable[[str], str],
    write_file: Callable[[str, str], dict],
    open_folder: Callable[[str], None] | None = None,
    open_file: Callable[[str], None] | None = None,
) -> dict:
    writes = {"n": 0}

    def _counted(rel: str, content: str) -> dict:
        writes["n"] += 1
        return write_file(rel, content)

    plan = prepare_image_code_pipe(
        text,
        attachments,
        project_root=project_root,
        workspace_root=workspace_root,
        search_roots=search_roots,
        list_editors=list_editors,
        open_folder=open_folder,
        open_file=open_file,
    )
    if plan["action"] == "passthrough":
        return {"handled": False, "message": "", "write_count": 0}
    if plan["action"] == "ask":
        return {"handled": True, "message": plan["message"], "write_count": 0}
    try:
        raw = extract(str(plan.get("image") or ""))
    except Exception:
        raw = ""
    outcome = commit_extracted_code(raw, rel=str(plan.get("rel") or ""), write_file=_counted)
    return {"handled": True, "message": outcome["message"], "write_count": writes["n"]}


def extract_image_code(
    image_path: str,
    *,
    model: str,
    ollama_base_url: str = "",
    api_base_url: str = "",
    api_key: str = "",
    auth_style: str = "bearer",
) -> str:
    """코드만 한 번. Hermes 스트림·tool_choice·options 는 쓰지 않는다."""
    path = Path(image_path)
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    if not data or not model:
        return ""
    if not api_base_url:
        from iris.infrastructure.ollama_client import OllamaClient

        return OllamaClient(ollama_base_url).chat_once_with_images(
            model, _CODE_ONLY_PROMPT, [data]
        )
    from iris.infrastructure.openai_compat_client import _http_json, normalize_base_url

    root = normalize_base_url(api_base_url)
    if not root:
        return ""
    mime = _MIME.get(path.suffix.lower(), "image/png")
    data_url = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
    body = {
        "model": model,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _CODE_ONLY_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
    }
    obj = _http_json(
        "POST",
        f"{root}/chat/completions",
        api_key=api_key,
        auth_style=auth_style,
        body=body,
        timeout=90.0,
    )
    choices = obj.get("choices") if isinstance(obj, dict) else None
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return ""
    message = choices[0].get("message") if isinstance(choices[0].get("message"), dict) else {}
    content = message.get("content") if isinstance(message, dict) else ""
    if isinstance(content, list):
        parts = [
            str(part.get("text") or "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        return "".join(parts)
    return str(content or "")


def start_image_extract(parent, image: str, *, on_text: Callable[[str], None], **kwargs):
    """추출만 백그라운드. 키는 채팅에 넣지 않는다."""
    from iris.ui.chat.image_extract_worker import ImageExtractWorker

    worker = ImageExtractWorker(image, kwargs, parent)
    worker.done.connect(on_text)
    worker.start()
    return worker
