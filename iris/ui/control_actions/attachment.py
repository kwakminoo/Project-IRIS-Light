"""Attachment original transfer actions backed by the active chat session."""

from __future__ import annotations

from typing import Any

from iris.system.control_surface import ActionRegistry, err_result, ok_result
from iris.ui.control_actions.attachment_resolve import (
    resolve_attachment_id,
    store_from_window,
)


def _store(window: Any):
    return store_from_window(window)


def _resolve_attachment_id(window: Any, token: str, action: str):
    return resolve_attachment_id(window, token, action)


def register_attachment_actions(window: Any, reg: ActionRegistry) -> None:
    def attachment_list(_args: dict[str, Any]) -> dict[str, Any]:
        refs = [ref.as_dict() for ref in _store(window).list_refs()]
        return ok_result("attachment.list", {"attachments": refs, "count": len(refs)})

    def attachment_copy_to(args: dict[str, Any]) -> dict[str, Any]:
        attachment_id = str(args.get("attachment_id") or "").strip()
        destination = str(args.get("destination") or "").strip()
        if not attachment_id or not destination:
            return err_result(
                "attachment.copy_to", "attachment_id와 destination이 필요합니다."
            )
        resolved, err = _resolve_attachment_id(window, attachment_id, "attachment.copy_to")
        if err is not None:
            return err
        target = _store(window).copy_to(
            resolved, destination, overwrite=bool(args.get("overwrite", False))
        )
        return ok_result("attachment.copy_to", {"path": str(target)})

    def attachment_move_to(args: dict[str, Any]) -> dict[str, Any]:
        attachment_id = str(args.get("attachment_id") or "").strip()
        destination = str(args.get("destination") or "").strip()
        if not attachment_id or not destination:
            return err_result(
                "attachment.move_to", "attachment_id와 destination이 필요합니다."
            )
        resolved, err = _resolve_attachment_id(window, attachment_id, "attachment.move_to")
        if err is not None:
            return err
        target = _store(window).move_to(
            resolved, destination, overwrite=bool(args.get("overwrite", False))
        )
        return ok_result("attachment.move_to", {"path": str(target)})

    def project_import_attachment(args: dict[str, Any]) -> dict[str, Any]:
        from iris.system.project_ops import resolve_under_root
        from iris.ui.control_bindings import resolve_bound_work_root

        attachment_id = str(args.get("attachment_id") or "").strip()
        rel_path = str(args.get("rel_path") or "").strip()
        if not attachment_id or not rel_path:
            return err_result(
                "project.import_attachment", "attachment_id와 rel_path가 필요합니다."
            )
        resolved, err = _resolve_attachment_id(
            window, attachment_id, "project.import_attachment"
        )
        if err is not None:
            return err
        root, root_error = resolve_bound_work_root(window, args)
        if root_error or not root:
            return err_result(
                "project.import_attachment",
                root_error or "bound IDE workspace required",
            )
        try:
            _root, target, relative = resolve_under_root(root, rel_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            copied = _store(window).copy_to(resolved, str(target), overwrite=False)
        except (FileExistsError, OSError, ValueError) as exc:
            return err_result("project.import_attachment", str(exc))
        return ok_result(
            "project.import_attachment",
            {"path": str(copied), "rel_path": relative, "bytes": copied.stat().st_size},
        )

    reg.register(
        "attachment.list",
        attachment_list,
        summary=(
            "List current chat attachments as {id, filename, size, mime}. "
            "Use id with attachment.copy_to / move_to / project.import_attachment; "
            "host paths are never returned."
        ),
        risk="low",
    )
    reg.register(
        "attachment.copy_to",
        attachment_copy_to,
        summary=(
            "Copy an attached original by attachment_id to an absolute destination. "
            "The source host path is never exposed; external writes require human confirmation. "
            "overwrite defaults to false."
        ),
        risk="medium",
        confirm_required=True,
    )
    reg.register(
        "attachment.move_to",
        attachment_move_to,
        summary=(
            "Move an attached original by attachment_id to an absolute destination. "
            "Call only when the user explicitly asked to move it; source deletion requires human confirmation."
        ),
        risk="high",
        confirm_required=True,
    )
    reg.register(
        "project.import_attachment",
        project_import_attachment,
        summary=(
            "Copy an attached original into the bound IDE workspace. "
            "Required: attachment_id and workspace-relative rel_path; existing files are refused."
        ),
        risk="medium",
    )
