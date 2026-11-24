"""H1 bakeoff throwaway: one QWebEngineView hosts the whole assistant turn."""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

ensure_qt_webengine_ready()

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PyQt6.QtWebEngineWidgets import QWebEngineView

HERE = Path(__file__).resolve().parent
SAMPLE = HERE.parent / "shared" / "sample_turn.json"
VERIFY = "--verify" in sys.argv


def _md_to_html(md: str) -> str:
    t = html.escape(md)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = t.replace("\n", "<br>\n")
    return t


def _build_page(turn: dict) -> str:
    blocks: list[str] = []
    for i, part in enumerate(turn.get("parts") or []):
        kind = part.get("type")
        if kind == "text":
            blocks.append(
                f'<section class="part text" data-part="{i}">'
                f'<div class="md">{_md_to_html(part.get("markdown") or "")}</div>'
                f"</section>"
            )
        elif kind == "writing":
            title = html.escape(part.get("title") or "")
            body = html.escape(part.get("body") or "")
            blocks.append(
                f'<section class="part writing" data-part="{i}">'
                f'<div class="label">writing</div>'
                f'<div class="writing-card" contenteditable="true" id="writing-{i}">'
                f'<div class="w-title">{title}</div>'
                f'<pre class="w-body">{body}</pre>'
                f"</div></section>"
            )
        elif kind == "code":
            src = part.get("source") or ""
            fname = html.escape(part.get("filename") or "snippet")
            lang = html.escape(part.get("language") or "")
            src_esc = html.escape(src)
            srcdoc = html.escape(src, quote=True)
            blocks.append(
                f'<section class="part code" data-part="{i}">'
                f'<div class="label">code · {fname} · {lang}</div>'
                f'<div class="tabs">'
                f'<button type="button" class="tab on" data-tab="code" data-target="codepane-{i}">Code</button>'
                f'<button type="button" class="tab" data-tab="preview" data-target="codepane-{i}">Preview</button>'
                f"</div>"
                f'<div class="codepane" id="codepane-{i}">'
                f'<textarea class="code-src" spellcheck="false">{src_esc}</textarea>'
                f'<iframe class="code-preview" sandbox="allow-scripts allow-same-origin" srcdoc="{srcdoc}" hidden></iframe>'
                f"</div></section>"
            )
        elif kind == "app":
            title = html.escape(part.get("title") or "app")
            app_html = part.get("html") or ""
            srcdoc = html.escape(app_html, quote=True)
            blocks.append(
                f'<section class="part app" data-part="{i}">'
                f'<div class="label">app · {title}</div>'
                f'<iframe class="app-frame" id="app-{i}" sandbox="allow-scripts allow-same-origin" srcdoc="{srcdoc}"></iframe>'
                f"</section>"
            )

    body = "\n".join(blocks)
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>H1 WebEngine transcript</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{
    margin: 0; padding: 16px 20px 40px;
    font: 15px/1.5 system-ui, sans-serif;
    background: #0b1220; color: #e5e7eb;
  }}
  .role {{ font-size: 12px; letter-spacing: .08em; text-transform: uppercase; color: #94a3b8; margin-bottom: 12px; }}
  .part {{ margin: 0 0 18px; padding: 14px; border: 1px solid #1f2937; border-radius: 12px; background: #111827; }}
  .label {{ font-size: 11px; color: #64748b; margin-bottom: 8px; text-transform: uppercase; letter-spacing: .06em; }}
  .md strong {{ color: #f8fafc; }}
  .writing-card {{
    min-height: 120px; padding: 12px; border-radius: 10px;
    background: #0f172a; border: 1px dashed #334155; outline: none;
  }}
  .writing-card:focus {{ border-color: #38bdf8; }}
  .w-title {{ font-weight: 700; margin-bottom: 8px; }}
  .w-body {{ margin: 0; white-space: pre-wrap; font: inherit; color: #cbd5e1; }}
  .tabs {{ display: flex; gap: 6px; margin-bottom: 8px; }}
  .tab {{
    padding: 6px 12px; border-radius: 8px; border: 1px solid #334155;
    background: #1e293b; color: #e2e8f0; cursor: pointer;
  }}
  .tab.on {{ background: #2563eb; border-color: #2563eb; }}
  .codepane textarea, .codepane iframe {{
    width: 100%; height: 220px; border: 0; border-radius: 8px;
    background: #020617; color: #e2e8f0; box-sizing: border-box;
  }}
  .codepane textarea {{ padding: 10px; font: 13px/1.4 ui-monospace, Consolas, monospace; resize: vertical; }}
  .app-frame {{ width: 100%; height: 180px; border: 0; border-radius: 8px; background: #020617; }}
</style>
</head>
<body>
  <div class="role">assistant · {html.escape(turn.get("id") or "")}</div>
  {body}
<script>
document.querySelectorAll('.tabs').forEach(group => {{
  group.addEventListener('click', (ev) => {{
    const btn = ev.target.closest('.tab');
    if (!btn) return;
    const pane = document.getElementById(btn.dataset.target);
    if (!pane) return;
    group.querySelectorAll('.tab').forEach(b => b.classList.toggle('on', b === btn));
    const code = pane.querySelector('.code-src');
    const prev = pane.querySelector('.code-preview');
    const showPreview = btn.dataset.tab === 'preview';
    if (code) code.hidden = showPreview;
    if (prev) {{
      prev.hidden = !showPreview;
      if (showPreview && code) prev.srcdoc = code.value;
    }}
  }});
}});
window.__h1_probe = function() {{
  const out = {{ writing: false, codePreview: false, calculator: false, detail: {{}} }};
  const w = document.querySelector('.writing-card');
  if (w) {{
    const before = w.innerText;
    w.focus();
    w.innerText = before + '\\n[h1-edit-ok]';
    out.writing = w.innerText.includes('[h1-edit-ok]');
    out.detail.writing = out.writing ? 'contenteditable accepted edit' : 'edit missing';
  }} else {{
    out.detail.writing = 'no writing card';
  }}
  const previewBtn = document.querySelector('.tab[data-tab="preview"]');
  const codeBtn = document.querySelector('.tab[data-tab="code"]');
  const pane = document.querySelector('.codepane');
  if (previewBtn && codeBtn && pane) {{
    previewBtn.click();
    const prev = pane.querySelector('.code-preview');
    const code = pane.querySelector('.code-src');
    const previewShown = !!(prev && !prev.hidden && code && code.hidden);
    codeBtn.click();
    const codeShown = !!(code && !code.hidden && prev && prev.hidden);
    out.codePreview = previewShown && codeShown;
    out.detail.codePreview = out.codePreview
      ? 'Code/Preview toggle ok'
      : ('toggle failed previewShown=' + previewShown + ' codeShown=' + codeShown);
  }} else {{
    out.detail.codePreview = 'missing tabs';
  }}
  const frame = document.querySelector('.app-frame');
  let doc = null;
  try {{ doc = frame && frame.contentDocument; }} catch (e) {{ out.detail.calculator = String(e); }}
  if (doc) {{
    const a = doc.getElementById('a');
    const b = doc.getElementById('b');
    const go = doc.getElementById('go');
    const result = doc.getElementById('out');
    if (a && b && go && result) {{
      a.value = '5';
      b.value = '7';
      go.click();
      out.calculator = (result.textContent || '').trim() === '= 12';
      out.detail.calculator = result.textContent;
    }} else {{
      out.detail.calculator = 'calc controls missing';
    }}
  }} else if (!out.detail.calculator) {{
    out.detail.calculator = 'iframe contentDocument unavailable';
  }}
  return out;
}};
</script>
</body>
</html>
"""


def main() -> int:
    turn = json.loads(SAMPLE.read_text(encoding="utf-8"))
    page = _build_page(turn)
    (HERE / "page.generated.html").write_text(page, encoding="utf-8")

    app = QApplication(sys.argv)
    win = QMainWindow()
    win.setWindowTitle("H1 · QWebEngineView transcript")
    win.resize(720, 900)
    host = QWidget()
    lay = QVBoxLayout(host)
    lay.setContentsMargins(0, 0, 0, 0)
    view = QWebEngineView(host)
    lay.addWidget(view)
    win.setCentralWidget(host)

    result: dict = {"ok": False, "probe": None, "error": None}

    def on_loaded(ok: bool) -> None:
        if not VERIFY:
            return
        if not ok:
            result["error"] = "loadFinished false"
            QTimer.singleShot(0, app.quit)
            return

        def after_probe(raw) -> None:
            probe = raw
            if isinstance(raw, str):
                try:
                    probe = json.loads(raw)
                except json.JSONDecodeError:
                    result["error"] = f"probe json fail: {raw!r}"
                    QTimer.singleShot(50, app.quit)
                    return
            result["probe"] = probe
            if isinstance(probe, dict) and probe:
                result["ok"] = bool(
                    probe.get("writing") and probe.get("codePreview") and probe.get("calculator")
                )
            else:
                result["error"] = f"bad probe: {probe!r}"
            QTimer.singleShot(50, app.quit)

        # srcdoc iframes need a beat before contentDocument is ready
        def run_probe() -> None:
            view.page().runJavaScript(
                "JSON.stringify(window.__h1_probe ? window.__h1_probe() : {error:'no probe'})",
                after_probe,
            )

        QTimer.singleShot(800, run_probe)

    view.loadFinished.connect(on_loaded)
    view.setHtml(page, QUrl.fromLocalFile(str(HERE / "index.html")))
    win.show()

    if not VERIFY:
        return app.exec()

    app.exec()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
