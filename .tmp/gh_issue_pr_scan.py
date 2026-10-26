import json
from pathlib import Path

issues = json.loads(Path(r"C:\Users\serin\.cursor\projects\c-Users-serin-Github-Project-IRIS-Light\agent-tools\e915035f-5998-4e7e-8521-5d1414037e82.txt").read_text(encoding="utf-8"))
prs = json.loads(Path(r"C:\Users\serin\.cursor\projects\c-Users-serin-Github-Project-IRIS-Light\agent-tools\5abc0618-705b-4c79-bc53-30e3bad5b3c4.txt").read_text(encoding="utf-8"))

out = Path(r"C:\Users\serin\Github\Project-IRIS-Light\.tmp\gh_issue_pr_scan.txt")
lines = []

def emit(*args):
    lines.append(" ".join(str(a) for a in args))

emit("ISSUES_COUNT", len(issues) if isinstance(issues, list) else type(issues))
emit("PRS_COUNT", len(prs) if isinstance(prs, list) else type(prs))

terms = [
    "browser intent",
    "match_browser_intent",
    "iris_invoke",
    "youtube",
    "hermes_owns_local_intents",
    "gemma",
    "tool calling",
    "local intercept",
    "browser.",
    "intent",
    "hermes",
    "webengine",
    "3658a305",
    "80d5e34f",
    "_try_local_browser",
    "local_browser",
    "브라우저",
    "유튜브",
    "재생",
    "intercept",
    "phrase",
    "high-confidence",
    "confidence",
    "tool call",
    "browser",
]


def hay(item):
    parts = [
        str(item.get("number")),
        item.get("title") or "",
        item.get("body") or "",
        item.get("html_url") or "",
        " ".join(l.get("name", "") for l in (item.get("labels") or [])),
    ]
    return "\n".join(parts).lower()


emit("===== ALL ISSUES =====")
for i in issues if isinstance(issues, list) else []:
    labels = [l.get("name") for l in (i.get("labels") or [])]
    emit(
        f"#{i.get('number')} [{i.get('state')}] {i.get('title')} "
        f"created={i.get('created_at')} updated={i.get('updated_at')} "
        f"labels={labels} pr={bool(i.get('pull_request'))} url={i.get('html_url')}"
    )

emit("===== ALL PR TITLES =====")
for p in prs if isinstance(prs, list) else []:
    merged = "merged" if p.get("merged_at") else "unmerged"
    head = ((p.get("head") or {}).get("ref"))
    emit(
        f"#{p.get('number')} [{p.get('state')}/{merged}] {p.get('title')} "
        f"created={p.get('created_at')} merged={p.get('merged_at')} "
        f"head={head} url={p.get('html_url')}"
    )

emit("===== MATCHES =====")
for name, items in [("ISSUE", issues), ("PR", prs)]:
    if not isinstance(items, list):
        continue
    for item in items:
        h = hay(item)
        hit = [t for t in terms if t.lower() in h]
        if hit:
            body = item.get("body") or ""
            emit(f"--- {name} #{item.get('number')} hits={hit} title={item.get('title')} ---")
            emit(body[:4000])
            emit()

out.write_text("\n".join(lines), encoding="utf-8")
print("wrote", out, "chars", out.stat().st_size)
