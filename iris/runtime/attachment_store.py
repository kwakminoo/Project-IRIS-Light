"""Session-owned attachment index and host-only tools. No arbitrary paths."""
from __future__ import annotations

import fnmatch
import os
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath

from .attachment_context import (
    Attachment, PreparedAttachments, EXCLUDED, TEXT_EXTENSIONS, TEXT_FILENAMES,
    MAX_FOLDER_ENTRIES, MAX_CONTEXT_CHARS, MAX_FILE_BYTES,
    MAX_FILES, _is_link, _read, query_terms,
)


@dataclass
class AttachedRoot:
    id: str
    path: Path
    directory: bool
    files: dict[str, dict] = field(default_factory=dict)
    error: str = ""
    truncated: bool = False


class AttachmentStore:
    """Capabilities exist only for explicitly registered files/folders.

    Paths are never restored from chat history. A new ChatSession owns a new
    store. Every read revalidates containment and rejects links/junctions.
    """

    def __init__(self, *, exclude_patterns=()):
        self.exclude_patterns = tuple(exclude_patterns)
        self.roots: dict[str, AttachedRoot] = {}

    def clear(self):
        self.roots.clear()

    def _excluded(self, name):
        return (name.casefold() in EXCLUDED or name.casefold().startswith((".venv-", ".iris_light_test_tmp"))
                or any(fnmatch.fnmatch(name, p) for p in self.exclude_patterns))

    @staticmethod
    def _directory_priority(name: str) -> tuple[int, str]:
        order = {"iris": 0, "src": 1, "app": 2, "integrations": 20, "lib": 30}
        folded = name.casefold()
        return order.get(folded, 10), folded

    @staticmethod
    def _generated_directory(root: Path, candidate: Path) -> bool:
        try:
            relative = candidate.relative_to(root).as_posix().casefold()
        except ValueError:
            return True
        return relative == "integrations/iris-ide/lib" or relative.startswith(
            "integrations/iris-ide/lib/"
        )

    def attach(self, paths, *, cancelled=lambda: False):
        for raw in paths:
            if cancelled():
                break
            path = Path(raw).expanduser().absolute()
            if any(root.path == path for root in self.roots.values()):
                continue
            if len(self.roots) >= MAX_FILES:
                limited = AttachedRoot("attachment-limit", path, False,
                    error="첨부 개수 한도에 도달했습니다 (최대 50개).")
                self.roots[limited.id] = limited
                break
            root = AttachedRoot(uuid.uuid4().hex, path, path.is_dir())
            self.roots[root.id] = root
            try:
                if _is_link(path):
                    raise ValueError("심볼릭 링크/정션은 첨부할 수 없습니다.")
                if not root.directory:
                    self._index(root, path.name, path)
                    continue
                def onerror(exc):
                    root.error = "폴더 일부를 읽을 권한이 없거나 삭제되었습니다."
                for directory, dirs, files in os.walk(path, followlinks=False, onerror=onerror):
                    dirs[:] = sorted(
                        (
                            d
                            for d in dirs
                            if not self._excluded(d)
                            and not _is_link(Path(directory) / d)
                            and not self._generated_directory(path, Path(directory) / d)
                        ),
                        key=self._directory_priority,
                    )
                    for name in sorted(files):
                        if cancelled() or len(root.files) >= MAX_FOLDER_ENTRIES:
                            root.truncated = True
                            break
                        candidate = Path(directory) / name
                        if not _is_link(candidate) and not self._excluded(name):
                            self._index(root, candidate.relative_to(path).as_posix(), candidate)
                    if cancelled() or len(root.files) >= MAX_FOLDER_ENTRIES:
                        root.truncated = True
                        break
                if root.truncated and not cancelled():
                    root.error = (root.error + " " if root.error else "") + "폴더 탐색 항목 한도에 도달했습니다 (최대 2,000개). 일부 파일은 인덱싱되지 않았습니다."
            except (OSError, ValueError) as exc:
                root.error = str(exc) if isinstance(exc, ValueError) else "파일이 삭제되었거나 경로/권한을 확인해야 합니다."

    def _index(self, root, relative, path):
        stat = path.stat()
        import mimetypes
        root.files[relative] = dict(file_name=path.name, full_path=str(path), relative_path=relative,
            extension=path.suffix.lower().lstrip("."), mime_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            size=stat.st_size, modified_time=stat.st_mtime, attachment_id=root.id,
            folder_root=str(root.path) if root.directory else "", extracted_text=False)

    def list_attached_files(self, attachment_id=None):
        roots = [self.roots[attachment_id]] if attachment_id else self.roots.values()
        return [dict(meta) for root in roots for meta in root.files.values()]

    def _resolve(self, attachment_id, relative_path):
        root = self.roots[attachment_id]
        relative = str(relative_path).replace("\\", "/")
        if (Path(relative).is_absolute() or PureWindowsPath(relative).drive
                or any(p in ("..", "", ".") for p in relative.split("/"))
                or ":" in relative or relative not in root.files):
            raise ValueError("첨부 범위 밖의 경로는 읽을 수 없습니다.")
        path = root.path / relative if root.directory else root.path
        base = root.path if root.directory else root.path.parent
        current = path
        while True:
            if _is_link(current):
                raise ValueError("심볼릭 링크/정션 접근은 허용되지 않습니다.")
            if current == base:
                break
            current = current.parent
        path.resolve().relative_to(base.resolve())
        return path

    def _transfer_source(self, attachment_id: str) -> tuple[AttachedRoot, Path, str]:
        root = self.roots.get(str(attachment_id or ""))
        if root is None:
            raise ValueError("첨부파일을 찾을 수 없습니다.")
        # ponytail: 원본 전송은 개별 파일만 지원한다. 폴더 전송 요구가 생기면 별도 확인 UX를 둔다.
        if root.directory:
            raise ValueError("폴더 첨부는 복사·이동할 수 없습니다. 파일을 개별 첨부해 주세요.")
        relative = next(iter(root.files), root.path.name)
        source = self._resolve(root.id, relative)
        if not source.is_file():
            raise ValueError("첨부파일 원본이 없거나 파일이 아닙니다.")
        return root, source, relative

    @staticmethod
    def _transfer_target(source: Path, destination: str | os.PathLike[str]) -> Path:
        raw = Path(destination).expanduser()
        if not raw.is_absolute():
            raise ValueError("destination은 절대경로여야 합니다.")
        target = raw / source.name if raw.is_dir() else raw
        if not target.parent.is_dir():
            raise ValueError("대상 폴더가 존재하지 않습니다.")
        if _is_link(target.parent) or (target.exists() and _is_link(target)):
            raise ValueError("심볼릭 링크/정션 대상에는 쓸 수 없습니다.")
        return target

    @staticmethod
    def _copy_atomic(source: Path, target: Path, *, overwrite: bool) -> None:
        if target.exists() and not overwrite:
            raise FileExistsError(f"대상 파일이 이미 존재합니다: {target.name}")
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            shutil.copy2(source, temporary)
            if overwrite:
                os.replace(temporary, target)
            else:
                # Atomic no-clobber: a late competing create must not be overwritten.
                os.link(temporary, target)
                temporary.unlink()
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def copy_to(self, attachment_id: str, destination: str, *, overwrite: bool = False) -> Path:
        """Copy one attached original without exposing its host source path."""
        _root, source, _relative = self._transfer_source(attachment_id)
        target = self._transfer_target(source, destination)
        if source.resolve() == target.resolve():
            raise ValueError("원본과 대상이 같습니다.")
        try:
            self._copy_atomic(source, target, overwrite=bool(overwrite))
        except FileExistsError:
            raise
        except OSError as exc:
            raise OSError("첨부파일을 대상 위치로 복사하지 못했습니다.") from exc
        return target

    def move_to(self, attachment_id: str, destination: str, *, overwrite: bool = False) -> Path:
        """Move one attached original; callers must obtain explicit human confirmation."""
        root, source, relative = self._transfer_source(attachment_id)
        target = self._transfer_target(source, destination)
        if source.resolve() == target.resolve():
            return target
        try:
            self._copy_atomic(source, target, overwrite=bool(overwrite))
        except FileExistsError:
            raise
        except OSError as exc:
            raise OSError("첨부파일을 대상 위치로 이동하지 못했습니다.") from exc
        try:
            source.unlink()
        except OSError as exc:
            raise OSError(
                "대상 복사는 완료됐지만 첨부 원본을 삭제하지 못해 이동을 완료하지 못했습니다."
            ) from exc
        root.path = target
        meta = root.files[relative]
        meta.update(
            file_name=target.name,
            full_path=str(target),
            relative_path=target.name,
            folder_root="",
        )
        if relative != target.name:
            root.files = {target.name: meta}
        return target

    def read_attached_file(self, attachment_id, relative_path, *, query="", budget=6000):
        path = self._resolve(attachment_id, relative_path)
        root = self.roots[attachment_id]
        item = _read(path, filename=f"{root.path.name}/{relative_path}" if root.directory else path.name,
                     budget=min(max(0, budget), MAX_CONTEXT_CHARS), query=query)
        item.id = attachment_id + ":" + relative_path
        item.attachment_id = attachment_id
        item.relative_path = relative_path
        item.folder_root = str(root.path) if root.directory else ""
        root.files[relative_path]["extracted_text"] = item.extracted_text
        return item

    def list_attached_directory(self, attachment_id, relative_path=""):
        prefix = relative_path.replace("\\", "/").strip("/")
        if ".." in prefix.split("/") or PureWindowsPath(prefix).drive:
            raise ValueError("첨부 범위 밖의 경로입니다.")
        return [m for m in self.list_attached_files(attachment_id)
                if not prefix or m["relative_path"].startswith(prefix + "/")]

    def search_attached_files(self, query, *, attachment_id=None, extension=None, limit=20, cancelled=lambda: False):
        terms = query_terms(query)
        hits = []
        scanned = 0
        for meta in self.list_attached_files(attachment_id):
            if cancelled():
                break
            if extension and meta["extension"] != extension.lstrip(".").lower():
                continue
            relative = meta["relative_path"]
            score = sum(100 for t in terms if t in relative.casefold())
            score += sum(50 for t in terms if t in {p.casefold() for p in Path(relative).parts[:-1]})
            if relative.casefold() in query.casefold():
                score += 200
            content_score = 0
            snippets = []
            # Bounded streaming literal search over text/code; documents are
            # extracted only after filename ranking, never all during indexing.
            if meta["extension"] in TEXT_EXTENSIONS or meta["file_name"].lower() in TEXT_FILENAMES:
                if meta["size"] <= MAX_FILE_BYTES and scanned + meta["size"] <= 60 * 1024 * 1024:
                    scanned += meta["size"]
                    try:
                        path = self._resolve(meta["attachment_id"], relative)
                        with path.open("r", encoding="utf-8-sig", errors="replace") as stream:
                            for number, line in enumerate(stream, 1):
                                if cancelled():
                                    break
                                matches = sum(1 for t in terms if t in line.casefold())
                                content_score = min(25, content_score + matches)
                                if matches and len(snippets) < 3:
                                    snippets.append(dict(line=number, text=line[:300].rstrip()))
                    except (OSError, ValueError):
                        pass
            score += content_score
            if score or extension:
                hits.append(dict(attachment_id=meta["attachment_id"], relative_path=relative, score=score, snippets=snippets))
        return sorted(hits, key=lambda h: (-h["score"], h["relative_path"]))[:max(0, min(limit, 50))]

    def read_file_chunk(self, attachment_id, relative_path, chunk_index=0):
        if not isinstance(chunk_index, int) or chunk_index < 0:
            raise ValueError("chunk_index는 0 이상의 정수여야 합니다.")
        from .attachment_context import _document_chunks
        path = self._resolve(attachment_id, relative_path)
        if not 0 < path.stat().st_size <= MAX_FILE_BYTES:
            raise ValueError("파일 크기 한도를 확인하세요.")
        for index, chunk in enumerate(_document_chunks(path)):
            if index == chunk_index:
                return chunk
        raise ValueError("요청한 chunk가 없습니다.")

    def prepare(self, query="", *, cancelled=lambda: False):
        items = []
        roots = list(self.roots.values())
        remaining = MAX_CONTEXT_CHARS
        for root in roots:
            if cancelled():
                break
            if root.directory:
                listing = "Folder files:\n" + "\n".join(root.files)
                budget = min(4000, remaining // max(1, len(roots)))
                items.append(Attachment(root.id, str(root.path), root.path.name, "inode/directory",
                    text=listing[:budget], error=root.error, truncated=root.truncated or len(listing) > budget,
                    attachment_id=root.id, folder_root=str(root.path)))
                remaining -= min(len(listing), budget)
        candidates = []
        for root in roots:
            if not root.directory:
                candidates.extend((root.id, relative) for relative in root.files)
                if root.error:
                    items.append(Attachment(root.id, str(root.path), root.path.name, "application/octet-stream", error=root.error))
            else:
                hits = self.search_attached_files(query, attachment_id=root.id, limit=50, cancelled=cancelled)
                code_query = any(word in query for word in ("코드", "구현", "함수", "호출")) and "readme" not in query.casefold()
                if code_query:
                    source_hits = [h for h in hits if root.files[h["relative_path"]]["extension"] in
                                   {"py", "pyw", "js", "jsx", "ts", "tsx", "java", "cs", "c", "h", "cpp", "go", "rs", "kt", "php", "rb", "swift"}]
                    if source_hits:
                        if "구현" in query:
                            implementation_hits = [h for h in source_hits
                                if not h["relative_path"].startswith("installer/payload/")
                                and not Path(h["relative_path"]).name.startswith(("_check_", "test_", "__init__"))]
                            named_hits = [h for h in implementation_hits if h["score"] >= 100]
                            source_hits = named_hits or implementation_hits or source_hits
                        hits = source_hits
                explicit = [h for h in hits if h["relative_path"].casefold() in query.casefold()]
                chosen = [h["relative_path"] for h in (explicit or hits)[:6]]
                if not chosen:
                    chosen = sorted(root.files, key=lambda p: (not p.lower().startswith("readme"), p))[:3]
                candidates.extend((root.id, p) for p in chosen)
        candidates = candidates[:MAX_FILES]
        per_file = remaining // max(1, len(candidates))
        for aid, relative in candidates:
            if cancelled():
                break
            try:
                item = self.read_attached_file(aid, relative, query=query, budget=per_file)
            except (OSError, ValueError) as exc:
                item = Attachment(aid, "", relative, "application/octet-stream", error="첨부 파일이 삭제되었거나 접근 범위를 벗어났습니다.")
            items.append(item)
        return PreparedAttachments(sorted(items, key=lambda a: a.mime_type == "inode/directory"))
