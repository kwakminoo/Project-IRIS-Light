"""Native memory actions for the authenticated Desktop turn."""

from iris.storage.database import Database
from iris.storage.memory import MemoryStore
from iris.system.control_surface import ActionRegistry
from iris.system.execution_context import ExecutionContext, host_execution_context


def _memory_owner() -> ExecutionContext:
    context = host_execution_context()
    if (context is None or context.source != "desktop" or context.principal != "iris.desktop"
            or context.inference_scope != "local_ollama"):
        raise ValueError("Iris memory requires a trusted Desktop turn using a local Ollama model")
    return context


def register_memory_actions(db: Database, registry: ActionRegistry) -> None:
    def search(args: dict) -> dict:
        context = _memory_owner()
        query = args.get("query")
        if not isinstance(query, str) or len(query) > 400:
            raise ValueError("memory search query must be text of at most 400 characters")
        store = MemoryStore(db)
        if not store.enabled(context):
            raise ValueError("Iris memory is disabled in Settings")
        return {"memories": store.search(context, query, limit=5)}

    def mutate(op: str, args: dict) -> dict:
        context = _memory_owner()
        content = args.get("content")
        if op in ("save", "update") and (not isinstance(content, str) or len(content) > 600):
            raise ValueError("memory content must be text of at most 600 characters")
        store = MemoryStore(db)
        if op == "save":
            scope, kind = args.get("scope"), args.get("type", "fact")
            if not isinstance(scope, str) or not isinstance(kind, str):
                raise ValueError("scope and kind are required")
            return store.create(context, scope, kind, content)
        return store.change(context, args.get("id"), args.get("revision"),
                            content=content if op == "update" else None)

    registry.register("memory.search", search, summary="Search personal Iris memory")
    for op, summary in (("save", "Save a new Iris memory"), ("update", "Update one Iris memory"),
                        ("delete", "Delete one Iris memory")):
        registry.register(f"memory.{op}", lambda args, op=op: mutate(op, args), summary=summary,
                          risk="high", confirm_required=True)
