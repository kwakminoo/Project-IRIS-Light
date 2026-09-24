"""프로필과 IDE 선호 컨트롤 액션."""

from __future__ import annotations

from iris.system.control_surface import (
    ActionRegistry,
)
from iris.ui.control_actions.hosts import ProfileHost

def register_profile_actions(window: ProfileHost, reg: ActionRegistry) -> None:
    from iris.ui.control_bindings import (
        Path,
        UserProfile,
        _log,
        _public_profile,
        err_result,
        ide_catalog,
        is_ide_installed,
        load_user_profile,
        ok_result,
        save_user_profile,
    )

    def profile_get(_a: dict[str, Any]) -> dict[str, Any]:
        return ok_result("profile.get", _public_profile(load_user_profile(window._db)))

    def profile_set(args: dict[str, Any]) -> dict[str, Any]:
        from iris.storage.user_profile import parse_project_parents

        profile = load_user_profile(window._db)
        fields = UserProfile.__dataclass_fields__
        changed: list[str] = []
        for key, val in args.items():
            if key in ("confirm",):
                continue
            if key not in fields:
                continue
            if key == "project_parents":
                profile.project_parents = parse_project_parents(val)
            else:
                setattr(profile, key, str(val or ""))
            changed.append(key)
        if "project_root" in changed and profile.project_root.strip():
            root = Path(profile.project_root).expanduser()
            if not root.is_dir():
                return err_result("profile.set", f"project_root not a directory: {profile.project_root}")
            profile.project_root = str(root.resolve())
        if "project_parents" in changed and profile.project_parents:
            cleaned: list[str] = []
            for raw in profile.project_parents:
                p = Path(raw).expanduser()
                if not p.is_dir():
                    return err_result(
                        "profile.set",
                        f"project_parents entry not a directory: {raw}",
                    )
                cleaned.append(str(p.resolve()))
            profile.project_parents = cleaned
        if "preferred_ide" in changed and profile.preferred_ide.strip():
            ide_id = profile.preferred_ide.strip().lower()
            profile.preferred_ide = ide_id
            if ide_id != "custom" and not is_ide_installed(ide_id, profile.ide_exe_path):
                return err_result("profile.set", f"IDE not installed: {ide_id}")
        save_user_profile(window._db, profile)
        _log(window, "profile.set", True)
        return ok_result("profile.set", {"changed": changed, "profile": _public_profile(profile)})

    def ide_set_preferred(args: dict[str, Any]) -> dict[str, Any]:
        ide_id = str(args.get("ide_id") or args.get("preferred_ide") or "").strip().lower()
        if not ide_id:
            return err_result("ide.set_preferred", "ide_id required")
        known = {s.id for s in ide_catalog()} | {"custom"}
        if ide_id not in known:
            return err_result("ide.set_preferred", f"unknown ide_id: {ide_id}", {"known": sorted(known)})
        profile = load_user_profile(window._db)
        if ide_id != "custom" and not is_ide_installed(ide_id, profile.ide_exe_path):
            return err_result("ide.set_preferred", f"IDE not installed: {ide_id}")
        profile.preferred_ide = ide_id
        if ide_id != "custom":
            profile.ide_exe_path = ""
        save_user_profile(window._db, profile)
        _log(window, "ide.set_preferred", True)
        return ok_result("ide.set_preferred", {"preferred_ide": ide_id})

    def ide_set_project_root(args: dict[str, Any]) -> dict[str, Any]:
        path = str(args.get("path") or args.get("project_root") or "").strip()
        if not path:
            return err_result("ide.set_project_root", "path required")
        root = Path(path).expanduser()
        if not root.is_dir():
            return err_result("ide.set_project_root", f"not a directory: {path}")
        profile = load_user_profile(window._db)
        profile.project_root = str(root.resolve())
        save_user_profile(window._db, profile)
        _log(window, "ide.set_project_root", True)
        return ok_result("ide.set_project_root", {"project_root": profile.project_root})

    def ide_list(_a: dict[str, Any]) -> dict[str, Any]:
        profile = load_user_profile(window._db)
        items = []
        for spec in ide_catalog():
            items.append(
                {
                    "id": spec.id,
                    "name": spec.name,
                    "installed": is_ide_installed(spec.id, ""),
                }
            )
        items.append(
            {
                "id": "custom",
                "name": "Custom",
                "installed": bool(profile.ide_exe_path and Path(profile.ide_exe_path).is_file()),
            }
        )
        return ok_result("ide.list", {"ides": items, "preferred_ide": profile.preferred_ide})

    reg.register("profile.get", profile_get, summary="Get user profile (no secrets)")

    reg.register(
        "profile.set",
        profile_set,
        summary="Set user profile fields: name preferred_ide project_root project_parents ide paths",
        risk="medium",
    )

    reg.register(
        "ide.set_preferred",
        ide_set_preferred,
        summary="Set preferred IDE id (cursor vscode pycharm … or custom)",
        risk="medium",
    )

    reg.register(
        "ide.set_project_root",
        ide_set_project_root,
        summary="Set project_root folder for IDE Companion / vibe coding",
        risk="medium",
    )

    reg.register("ide.list", ide_list, summary="List IDE catalog and install status")
