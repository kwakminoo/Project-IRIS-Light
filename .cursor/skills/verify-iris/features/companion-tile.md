# Companion tile

Companion tile proves the IRIS IDE + Iris 80:20 split stays flush (no seam gap or overlap) and companion chrome wiring stays correct.

## Sub-features

- `tile-math` asserts `ide.width + iris.width == work.width` and flush edges.
- `tile-ratio` asserts ide width is `int(work.width * 0.8)`.
- `orb-embed` asserts companion layout embeds the visualizer without orphan top-level windows.

## How to get to it (user POV)

- Open a folder in IRIS IDE so Iris docks as companion on the right.
- Drag or retile; the two windows should meet with no gap.

## Driving it with verify-iris

Preconditions:

- `doctor.py` reports `ok: true`.
- Headless Qt available (no live IDE required for this prove).

- **Run prove.** `.\.venv\Scripts\python.exe .cursor\skills\verify-iris\scripts\prove_feature.py --feature companion-tile`
- **Observe.** Exit code `0`. Evidence under `.../companion-tile/report.json` with `"ok": true`.
- **Live optional.** If Iris + IRIS IDE are already tiled, visually confirm flush; do not use Win32 `SetWindowPos` on the Qt Iris window during verification.

## Gotchas

- `place_qt_window` must use `setGeometry` only. Mixing Win32 DPI placement regresses the ratio.
- Seam overlap helpers were removed on purpose. Do not reintroduce them to “fix” a gap.
- Orphan `QWidget` with `parent=None` + `show()` creates a blank Iris Light window. Fail the run if that appears.
