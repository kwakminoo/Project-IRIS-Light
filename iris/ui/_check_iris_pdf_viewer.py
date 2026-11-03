"""Assert Iris PDF viewer wiring (sources + bundle markers + vendor assets)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IDE = ROOT / "integrations" / "iris-ide"


def main() -> None:
    poller = (IDE / "src/browser/iris-ide-bridge-poller.ts").read_text(encoding="utf-8")
    assert "viewer: 'iris.pdf'" in poller or 'viewer: "iris.pdf"' in poller
    assert "isPdf" in poller
    assert "editorManager.open" in poller

    module = (IDE / "src/browser/iris-ide-frontend-module.ts").read_text(encoding="utf-8")
    assert "IrisPdfOpenHandler" in module
    assert "IRIS_PDF_WIDGET_FACTORY_ID" in module
    assert "IrisIdeStartContribution" in module

    assert (IDE / "vendor/pdfjs/pdf.mjs").is_file()
    assert (IDE / "vendor/pdfjs/pdf.worker.mjs").is_file()

    widget = (IDE / "src/browser/iris-pdf-widget.ts").read_text(encoding="utf-8")
    assert "getDocument" in widget
    assert "pdfjs/pdf.mjs" in widget

    handler = (IDE / "src/browser/iris-pdf-open-handler.ts").read_text(encoding="utf-8")
    assert ".pdf" in handler
    assert "500" in handler

    bindings = (ROOT / "iris/ui/control_bindings.py").read_text(encoding="utf-8")
    assert 'viewer not in ("iris.pdf", "monaco")' in bindings or "iris.pdf" in bindings

    for label, bundle in (
        ("workspace", IDE / "lib/frontend/bundle.js"),
        ("install", Path.home() / ".iris-light/runtimes/iris-ide/lib/frontend/bundle.js"),
    ):
        if not bundle.is_file():
            print(f"skip bundle check ({label} missing)")
            continue
        text = bundle.read_text(encoding="utf-8", errors="ignore")
        for marker in (
            "iris.ide.openFolder",
            "ide.pick_open_folder",
            "iris.ide.showStartScreen",
            "iris.ide.runFile",
            "IRIS_EXIT:",
            "iris.pdf",
            "iris-pdf",
        ):
            assert marker in text, f"{label} bundle missing {marker}"
        pdfjs = bundle.parent / "pdfjs" / "pdf.mjs"
        assert pdfjs.is_file(), f"{label} pdfjs missing: {pdfjs}"
        print(f"ok bundle+pdfjs {label}")

    print("ok iris pdf viewer wiring")


if __name__ == "__main__":
    main()
