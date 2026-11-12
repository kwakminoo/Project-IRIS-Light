"""Attachment original transfer actions backed by the active chat session."""

from __future__ import annotations

from typing import Any

from iris.system.control_surface import ActionRegistry, err_result, ok_result


def _store(window: Any):
    session = getattr(window, "_chat_session", None)
    store = getattr(session, "attachments", None)
    if store is None:
        raise ValueError("현재 채팅의 첨부 저장소를 찾을 수 없습니다.")
    return store


def register_attachment_actions(window: Any, reg: ActionRegistry) -> None:
    def attachment_copy_to(args: dict[str, Any]) -> dict[str, Any]:
        attachment_id = str(args.get("attachment_id") or "").strip()
        destination = str(args.get("destination") or "").strip()
        if not attachment_id or not destination:
            return err_result(
                "attachment.copy_to", "attachment_id와 destination이 필요합니다."
            )
        target = _store(window).copy_to(
            attachment_id, destination, overwrite=bool(args.get("overwrite", False))
        )
        return ok_result("attachment.copy_to", {"path": str(target)})

    def attachment_move_to(args: dict[str, Any]) -> dict[str, Any]:
        attachment_id = str(args.get("attachment_id") or "").strip()
        destination = str(args.get("destination") or "").strip()
        if not attachment_id or not destination:
            return err_result(
                "attachment.move_to", "attachment_id와 destination이 필요합니다."
            )
        target = _store(window).move_to(
            attachment_id, destination, overwrite=bool(args.get("overwrite", False))
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
        root, root_error = resolve_bound_work_root(window, args)
        if root_error or not root:
            return err_result(
                "project.import_attachment",
                root_error or "bound IDE workspace required",
            )
        try:
            _root, target, relative = resolve_under_root(root, rel_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            copied = _store(window).copy_to(attachment_id, str(target), overwrite=False)
        except (FileExistsError, OSError, ValueError) as exc:
            return err_result("project.import_attachment", str(exc))
        return ok_result(
            "project.import_attachment",
            {"path": str(copied), "rel_path": relative, "bytes": copied.stat().st_size},
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
