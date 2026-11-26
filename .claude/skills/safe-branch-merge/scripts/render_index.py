#!/usr/bin/env python3
"""
render_index.py — one page listing every merge report in a reports folder (default ~/Downloads/merge-reports).

Writes <reports folder>/index.html: per report the date, repository, source → target, status, item counts,
who decided, verification result, build result, and links to report.html / report.md.
Also lists the files that needed a person in more than one report of the same repository ("hotspots").
render_report.py calls it after every render; it can also be run on its own:

Usage: render_index.py [<reports folder>]
"""
import collections, datetime, glob, html, json, os, sys


def esc(s):
    return html.escape(str(s if s is not None else ""))


def load(p):
    try:
        return json.load(open(p))
    except (OSError, json.JSONDecodeError):
        return None


def summary(folder):
    d = load(os.path.join(folder, "analysis.json"))
    if not d:
        return None
    items = d.get("items") or []
    v = load(os.path.join(folder, "verification.json")) or {}
    b = load(os.path.join(folder, "build-summary.json")) or {}
    q = load(os.path.join(folder, "quality.json")) or {}
    res = b.get("results") or []
    t = d.get("target") or {}
    return {
        "id": os.path.basename(folder), "at": d.get("generated_at") or "", "status": d.get("status") or "",
        "repo": os.path.basename((t.get("repo_root") or t.get("folder") or "").rstrip("/")),
        "src": (d.get("source") or {}).get("branch"), "tgt": t.get("branch"),
        "items": len(items), "need": sum(1 for i in items if i.get("needs_decision_orig") or i.get("needs_decision")),
        "ai": sum(1 for i in items if i.get("decided_by") == "ai"),
        "dev": sum(1 for i in items if i.get("decision") and i.get("decided_by") not in (None, "", "ai")),
        "open": sum(1 for i in items if i.get("needs_decision") and not i.get("decision")),
        "people": sorted({n for i in items for n in (i.get("reviewed_by_developer") or [])}),
        "verify": None if not v else ("PASS" if v.get("ok") else "FAIL") + (f' · {v.get("missing_items")} missing' if v.get("missing_items") else "")
                  + (f' · {v.get("still_present_items")} still present' if v.get("still_present_items") else ""),
        "build": None if not res else f'{sum(1 for r in res if r.get("status") == "SUCCEEDED")}/{len(res)} schemes'
                 + ("" if b.get("all_succeeded") else " · FAILED: " + ", ".join(r["scheme"] for r in res if r.get("status") != "SUCCEEDED")),
        "build_ok": b.get("all_succeeded") if res else None,
        "risk_high": sum(1 for f in (q.get("files") or {}).values() if f.get("level") == "high") if q else None,
        "html": os.path.exists(os.path.join(folder, "report.html")), "md": os.path.exists(os.path.join(folder, "report.md")),
        "hot": {(i.get("target_path") or i.get("file")) for i in items if i.get("needs_decision_orig") or i.get("needs_decision")},
    }


CSS = """
:root{--bg:#f4f6f8;--card:#fff;--ink:#1c2430;--mut:#6b7785;--line:#dde3ea;--head:#eef2f6;--ok:#1b5e20;--okb:#e8f5e9;--bad:#b71c1c;--badb:#fdecea;--warn:#8a5a00;--warnb:#fff8e1;--link:#1565c0}
@media (prefers-color-scheme:dark){:root{--bg:#0f141a;--card:#161d25;--ink:#d7dee6;--mut:#8b98a7;--line:#2a3440;--head:#1d2630;--ok:#9be0a5;--okb:#132718;--bad:#ff9e9e;--badb:#2d1616;--warn:#ffcf70;--warnb:#2b2510;--link:#7cb7ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1400px;margin:0 auto;padding:24px 16px}h1{margin:0 0 4px;font-size:24px}h2{font-size:18px;margin:28px 0 10px}a{color:var(--link)}
.muted{color:var(--mut)}input{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:6px;padding:6px 10px;width:min(360px,100%)}
.tw{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:10px}table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{background:var(--head);position:sticky;top:0}
.c{display:inline-block;font-size:11px;font-weight:700;padding:1px 8px;border-radius:10px;background:var(--head);white-space:nowrap}
.c.ok{background:var(--okb);color:var(--ok)}.c.bad{background:var(--badb);color:var(--bad)}.c.warn{background:var(--warnb);color:var(--warn)}
code{font:12px SFMono-Regular,Menlo,monospace}
"""


def main():
    root = os.path.abspath(os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/Downloads/merge-reports"))
    rows = [r for r in (summary(f) for f in sorted(glob.glob(os.path.join(root, "*"))) if os.path.isdir(f)) if r]
    rows.sort(key=lambda r: r["at"], reverse=True)

    def chip(txt, ok):
        return f'<span class="c {"ok" if ok else "bad" if ok is False else ""}">{esc(txt)}</span>' if txt else '<span class="muted">—</span>'
    trs = []
    for r in rows:
        st = r["status"]
        stc = "ok" if st in ("MERGED_UNCOMMITTED", "AUTO_DECIDED", "DECISIONS_RECEIVED") else "warn" if st else ""
        q = esc((r["id"] + " " + r["repo"] + " " + str(r["src"]) + " " + str(r["tgt"]) + " " + st).lower())
        open_c = '<span class="c bad">%d open</span>' % r["open"] if r["open"] else ""
        people = esc(", ".join(r["people"])) or '<span class="muted">—</span>'
        if r["risk_high"]:
            risk = '<span class="c bad">%d high</span>' % r["risk_high"]
        else:
            risk = "0" if r["risk_high"] == 0 else '<span class="muted">—</span>'
        links = ('<a href="%s/report.html">report</a>' % esc(r["id"]) if r["html"] else "") + \
                (' · <a href="%s/report.md">md</a>' % esc(r["id"]) if r["md"] else "")
        verify = chip(r["verify"], (r["verify"] or "").startswith("PASS") if r["verify"] else None)
        trs.append(
            f'<tr data-q="{q}"><td>{esc(r["at"][:16].replace("T", " "))}</td><td><b>{esc(r["repo"])}</b></td>'
            f'<td><code>{esc(r["src"])}</code> → <code>{esc(r["tgt"])}</code><div class="muted" style="font-size:11px">{esc(r["id"])}</div></td>'
            f'<td><span class="c {stc}">{esc(st)}</span> {open_c}</td>'
            f'<td>{r["items"]} items · {r["need"]} needed a person<div class="muted">AI decided {r["ai"]} · developers {r["dev"]}</div></td>'
            f'<td>{people}</td><td>{verify}</td><td>{chip(r["build"], r["build_ok"])}</td><td>{risk}</td><td>{links}</td></tr>')
    hot = collections.defaultdict(list)
    for r in rows:
        for f in r["hot"]:
            hot[(r["repo"], f)].append(r)
    hots = sorted(((k, v) for k, v in hot.items() if len(v) > 1), key=lambda kv: -len(kv[1]))
    hot_html = ("<div class='tw'><table><tr><th>Repository</th><th>File</th><th>Reports</th></tr>" + "".join(
        f'<tr><td>{esc(repo)}</td><td><code>{esc(f)}</code></td><td><b>{len(v)}</b> — '
        + ", ".join(f'<a href="{esc(x["id"])}/report.html">{esc(x["at"][:10])}</a>' for x in v) + "</td></tr>" for (repo, f), v in hots[:100])
        + "</table></div>") if hots else '<p class="muted">No file has needed a person in more than one report of the same repository yet.</p>'
    page = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Merge reports</title><style>{CSS}</style></head><body><div class="wrap">
<h1>Merge reports</h1><div class="muted">{len(rows)} reports in <code>{esc(root)}</code> · updated {esc(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))} · generated by the safe-branch-merge skill</div>
<p><input id="f" type="search" placeholder="Filter by repository, branch, status…" oninput="const q=this.value.toLowerCase();document.querySelectorAll('tr[data-q]').forEach(r=>r.style.display=r.dataset.q.includes(q)?'':'none')"></p>
<div class="tw"><table><tr><th>Generated</th><th>Repository</th><th>Source → Target</th><th>Status</th><th>Items</th><th>Reviewed by</th><th>Verification</th><th>Build</th><th>High-risk files</th><th></th></tr>
{"".join(trs) or '<tr><td colspan="10">No reports yet.</td></tr>'}</table></div>
<h2>Hotspots across reports</h2><p class="muted">Files that needed a person in more than one merge of the same repository.</p>{hot_html}
</div></body></html>"""
    out = os.path.join(root, "index.html")
    with open(out, "w") as f:
        f.write(page)
    print(f"written: {out} ({len(rows)} reports)")


if __name__ == "__main__":
    main()
