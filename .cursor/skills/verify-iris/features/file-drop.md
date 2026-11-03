# File drop

File drop proves Iris can accept paths from IRIS IDE / OS drop and that the installed IDE frontend bundle still contains the Iris open-folder and drag bridge markers.

## Sub-features

- `bundle-markers` require workspace and install bundles to contain Iris IDE bridge strings.
- `drop-wiring` exercises file-drop checks used by companion drag.

## How to get to it (user POV)

- Drag a file or folder from IRIS IDE into Iris chat / open handlers.
- Use File → Open Folder / Open File in IRIS IDE.

## Driving it with verify-iris

Preconditions:

- `doctor.py` reports `ok: true`.
- After IDE source edits, run workspace IDE sync first (see Gotchas).

- **Run prove.** `.\.venv\Scripts\python.exe .cursor\skills\verify-iris\scripts\prove_feature.py --feature file-drop`
- **Observe.** Exit code `0`. Evidence `report.json` `"ok": true`.

## Gotchas

- Editing `integrations/iris-ide/lib/browser/*.js` alone does not update `~/.iris-light/runtimes/iris-ide/.../bundle.js`. Sync with `IrisIdeRuntimeManager.sync_workspace_build` before trusting live IDE.
- `QFileDialog` parents must stay `None` on frameless MainWindow paths or Qt can abort.
