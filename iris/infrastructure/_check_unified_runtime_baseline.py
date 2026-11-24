"""U00 — Unified Agent Runtime baseline inventory (regenerable, HEAD-independent).

Asserts facts the baseline doc cites: PIN text, PHASE4 / absorbed / strip counts,
InternalSidecar default, seed registry size, surface filter size.

Run:
  .venv\\Scripts\\python.exe -m iris.infrastructure._check_unified_runtime_baseline
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PIN_PATH = ROOT / "vendor" / "iris-agent-runtime" / "PIN"

# Contract numbers for this baseline epoch (U00). Update only when inventory intent changes.
EXPECTED_PIN = "a382af23f4c067d23463b5781958684c2cda82bc"
EXPECTED_PHASE4 = 116  # +project.apply_patch (U06)
EXPECTED_ABSORBED = 8  # +apply_patch → project.apply_patch
EXPECTED_STRIP = 15  # patch left STRIP_ONLY when absorbed as apply_patch alias
EXPECTED_SEED = 9
EXPECTED_HOME_ONLY = frozenset({"shell.run"})
EXPECTED_ABSORBED_NAMES = frozenset(
    {
        "terminal",
        "process_manage",
        "write_file",
        "read_file",
        "search_files",
        "apply_patch",
        "web_search",
        "web_extract",
    }
)


def inventory_snapshot() -> dict[str, object]:
    from iris.config.settings import load_settings
    from iris.engine.types import InternalSidecar, parse_engine_source
    from iris.infrastructure.absorbed_tool_aliases import (
        ABSORBED_TOOLS,
        STRIP_ONLY_NAMES,
        model_names,
        strip_only_names,
    )
    from iris.infrastructure.agent_tool_registry import default_registry
    from iris.infrastructure.speak_capability import (
        HOME_ONLY_SPEAK_ACTIONS,
        PHASE4_ALLOWLIST,
        engine_tool_schemas,
        grants_for_surface,
    )

    pin = PIN_PATH.read_text(encoding="utf-8").strip()
    reg = default_registry()
    catalog = reg.catalog()
    seed_names = sorted(row["name"] for row in catalog)
    source = parse_engine_source(load_settings())
    home_n = len(grants_for_surface(PHASE4_ALLOWLIST, "home"))
    ide_n = len(grants_for_surface(PHASE4_ALLOWLIST, "ide_companion"))
    return {
        "pin": pin,
        "phase4": len(PHASE4_ALLOWLIST.grants),
        "absorbed": len(ABSORBED_TOOLS),
        "absorbed_names": sorted(model_names()),
        "strip": len(STRIP_ONLY_NAMES),
        "strip_names": sorted(strip_only_names()),
        "seed": len(seed_names),
        "seed_names": seed_names,
        "mcp_bridge_seed": sum(1 for row in catalog if row.get("call_path") != "native"),
        "engine_source": type(source).__name__,
        "internal_sidecar": isinstance(source, InternalSidecar),
        "home_only": sorted(HOME_ONLY_SPEAK_ACTIONS),
        "surface_home_grants": home_n,
        "surface_ide_grants": ide_n,
        "engine_schema_home": len(engine_tool_schemas("home")),
        "engine_schema_ide": len(engine_tool_schemas("ide_companion")),
    }


def main() -> None:
    snap = inventory_snapshot()

    assert PIN_PATH.is_file(), PIN_PATH
    assert snap["pin"] == EXPECTED_PIN, snap["pin"]
    assert snap["phase4"] == EXPECTED_PHASE4, snap["phase4"]
    assert snap["absorbed"] == EXPECTED_ABSORBED, snap["absorbed"]
    assert frozenset(snap["absorbed_names"]) == EXPECTED_ABSORBED_NAMES
    assert snap["strip"] == EXPECTED_STRIP, snap["strip"]
    assert "process_manage" not in snap["strip_names"]
    assert "process_manage" in snap["absorbed_names"]
    assert "patch" not in snap["strip_names"]
    assert "apply_patch" in snap["absorbed_names"]
    assert "patch" not in snap["absorbed_names"]  # internal alias only
    assert snap["seed"] == EXPECTED_SEED, snap["seed"]
    assert snap["mcp_bridge_seed"] == 0, snap["mcp_bridge_seed"]
    assert snap["internal_sidecar"] is True
    assert snap["engine_source"] == "InternalSidecar"
    assert frozenset(snap["home_only"]) == EXPECTED_HOME_ONLY
    assert snap["surface_home_grants"] == EXPECTED_PHASE4
    assert snap["surface_ide_grants"] == EXPECTED_PHASE4 - len(EXPECTED_HOME_ONLY)
    # terminal absorbs shell.run|project.run into one model name per surface
    assert snap["engine_schema_home"] == EXPECTED_PHASE4 - 1
    assert snap["engine_schema_ide"] == EXPECTED_PHASE4 - 1

    print("unified_runtime_baseline ok")
    for key in (
        "pin",
        "phase4",
        "absorbed",
        "strip",
        "seed",
        "engine_source",
        "surface_home_grants",
        "surface_ide_grants",
        "engine_schema_home",
        "engine_schema_ide",
    ):
        print(f"  {key}={snap[key]}")


if __name__ == "__main__":
    main()
