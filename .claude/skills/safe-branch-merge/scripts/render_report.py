#!/usr/bin/env python3
"""
render_report.py — turn analysis.json into the developer discussion report.

Writes, next to analysis.json:
  report.html   self-contained page: decision cards, side-by-side snippets, AI recommendation,
                per-item decision + notes, "Export decisions" button (downloads decisions-<ID>.json)
  report.md     the same content in Markdown with [ ] checkboxes developers can tick by hand

Usage: render_report.py <report_folder>/analysis.json
"""
import html, json, os, sys, datetime

CAT_INFO = {
    "CONFLICT":          ("#c62828", "Both branches changed the same code. A person must choose."),
    "MAPPING_UNCERTAIN": ("#d84315", "Can't tell which target file holds this code — confirm the file first; nothing was compared."),
    "SYMBOL_NOT_FOUND":  ("#bf360c", "Source changed a function/type that target no longer has (removed, renamed or rewritten elsewhere)."),
    "NEW_SYMBOL":        ("#2e7d32", "New function/type from source — add it next to its type in the target file shown."),
    "VENDORED_BUNDLE":   ("#6d4c41", "Vendored .xcframework/.framework/.bundle — handled as one unit (keep, replace, or removed for a package)."),
    "DELETED_IN_TARGET": ("#ad1457", "Source changed code in a file target removed or moved beyond recognition."),
    "DELETED_IN_SOURCE": ("#ad1457", "Source deleted a file that target still has (and may have changed)."),
    "PROTECTED":         ("#6a1b9a", "Branch-specific file (package pins, entitlements, client config)."),
    "PROJECT_FILE":      ("#4527a0", "Xcode project membership / packages changed."),
    "RESTRUCTURED":      ("#1565c0", "File lives at a different path in target — change must be ported."),
    "OPTIMIZED_IN_TARGET": ("#00838f", "Target has a refactored/optimised version; source logic must be re-expressed in it."),
    "OPTIMIZED_IN_SOURCE": ("#00838f", "Source brings an optimised version of code target also changed."),
    "NEW_FILE":          ("#2e7d32", "New file from source — needs a folder and Xcode targets in target."),
    "NEAR_CHANGE":       ("#ef6c00", "Merges cleanly, but target changed code right next to it — check the logic still fits."),
    "BINARY":            ("#5d4037", "Binary asset — git cannot merge it."),
    "LARGE_FILE":        ("#5d4037", "Very large file — review with a diff tool."),
    "CLEAN":             ("#607d8b", "Source-only change; target untouched here. Will be applied as is."),
    "ALREADY_PRESENT":   ("#90a4ae", "Already in target (same or equivalent change)."),
    "COSMETIC":          ("#b0bec5", "Whitespace / formatting only."),
}
SEV_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}
OPTIONS = ["SOURCE", "TARGET", "BOTH", "AI", "CUSTOM"]
DEFAULT_LABELS = {"SOURCE": "Take incoming (source)", "TARGET": "Keep current (target)", "BOTH": "Keep both logics",
                  "AI": "Apply AI proposal", "CUSTOM": "Custom — see notes"}
CAT_LABELS = {
    "NEW_FILE": {"SOURCE": "Add file (suggested path)", "TARGET": "Do not add", "BOTH": "Add at another path (notes)"},
    "DELETED_IN_SOURCE": {"SOURCE": "Delete in target too", "TARGET": "Keep the file", "BOTH": "Keep, but apply notes"},
    "DELETED_IN_TARGET": {"SOURCE": "Port change into target", "TARGET": "Drop — removal was intentional", "BOTH": "Restore file + change"},
    "PROTECTED": {"SOURCE": "Use source values", "TARGET": "Keep target values", "BOTH": "Merge values (notes)"},
    "PROJECT_FILE": {"SOURCE": "Re-add source refs/targets", "TARGET": "Keep target project only", "BOTH": "Re-add, keep target packages"},
    "MAPPING_UNCERTAIN": {"SOURCE": "Port into the guessed file", "TARGET": "Not needed in target", "BOTH": "Port into file named in notes"},
    "SYMBOL_NOT_FOUND": {"SOURCE": "Port it (where: notes / AI proposal)", "TARGET": "Obsolete — drop it", "BOTH": "Re-add it as before"},
    "NEW_SYMBOL": {"SOURCE": "Add it to the shown file", "TARGET": "Don't add", "BOTH": "Add it elsewhere (notes)"},
    "VENDORED_BUNDLE": {"SOURCE": "Take source bundle", "TARGET": "Keep target (removed / package)", "BOTH": "Update the package pin instead (notes)"},
}


def esc(s):
    return html.escape(str(s if s is not None else ""))


def labels_for(cat):
    d = dict(DEFAULT_LABELS); d.update(CAT_LABELS.get(cat, {})); return d


def ranges(nums):
    nums = sorted(set(nums or []))
    out, a, b = [], None, None
    for n in nums:
        if a is None:
            a = b = n
        elif n == b + 1:
            b = n
        else:
            out.append((a, b)); a = b = n
    if a is not None:
        out.append((a, b))
    return ", ".join(f"L{x}" if x == y else f"L{x}-{y}" for x, y in out)


def code_block(snip, cls):
    if not snip:
        return '<div class="code empty">— not present —</div>'
    marked = set(snip.get("marked", []))
    owners = snip.get("authors") or {}
    rows = []
    for i, line in enumerate(snip.get("lines", [])):
        who = owners.get(str(i), "")
        rows.append(f'<tr class="{cls if i in marked else ""}"><td class="ln">{snip["start"] + i}</td>'
                    f'<td class="who" title="{esc(who)}">{esc(who)}</td><td class="lc">{esc(line) or "&nbsp;"}</td></tr>')
    return f'<table class="code">{"".join(rows)}</table>'


def person(p, with_commit=True):
    lines = f' — <b>{esc(p.get("role", ""))}</b>' if p.get("role") else ""
    if p.get("line_numbers"):
        lines += f' <span class="lines">{esc(ranges(p["line_numbers"]))}</span>'
    if p.get("base_line_numbers"):
        lines += f' <span class="lines" title="lines removed from the common ancestor">base {esc(ranges(p["base_line_numbers"]))}</span>'
    if p.get("committer"):
        lines += f' <span class="muted">(committed by {esc(p["committer"])})</span>'
    port = ""
    if p.get("ported_from"):
        o = p["ported_from"]
        port = (f'<div class="muted">↳ ported/cherry-picked from <code>{esc(o["short"])}</code> by <b>{esc(o["name"])}</b> '
                f'&lt;{esc(o["email"])}&gt; {esc(o["date"])} — {esc(o["subject"])}</div>')
    commit = f' — {esc(p.get("date"))} — <code>{esc(p.get("short"))}</code> {esc(p.get("subject"))}' if with_commit else ""
    note = f' <span class="muted">({esc(p["note"])})</span>' if p.get("note") else ""
    return f'<div class="dev"><b>{esc(p.get("name"))}</b> &lt;{esc(p.get("email"))}&gt;{lines}{commit}{note}{port}</div>'


def people(lst):
    if not lst:
        return '<span class="muted">—</span>'
    out = [person(p) for p in lst[:6]]
    if len(lst) > 6:
        out.append(f'<div class="muted">+{len(lst) - 6} more commit(s)</div>')
    return "".join(out)


def badge(cat):
    color = CAT_INFO.get(cat, ("#455a64", ""))[0]
    return f'<span class="badge" style="background:{color}">{esc(cat)}</span>'


def item_card(it, decision_ui=True):
    cat = it.get("ai_category") or it["category"]
    lab = labels_for(cat)
    m = it.get("mapping") or {}
    path_line = f'<code>{esc(it["file"])}</code>'
    if it.get("target_path") and it["target_path"] != it["file"]:
        path_line += f' → <code>{esc(it["target_path"])}</code>'
    elif not it.get("target_path") and it["category"] != "NEW_FILE":
        path_line += ' → <b class="warn">not found in target</b>'
    if it.get("compare") == "symbol":
        path_line += (f'<div>Compared by function: <code>{esc(it.get("source_symbol"))}</code> → '
                      f'<code>{esc(it.get("target_symbol") or "not in target")}</code> in <code>{esc(it.get("target_path") or "?")}</code></div>')
    if it.get("xcode_targets") or it.get("spm_target"):
        path_line += (f'<div>Add to build: Xcode targets <b>{esc(", ".join(it.get("xcode_targets") or []) or "—")}</b> · '
                      f'SPM target <b>{esc(it.get("spm_target") or "—")}</b></div>')
    if it.get("guessed_target_path"):
        path_line += f'<div class="warn">Unconfirmed guess (NOT compared): <code>{esc(it["guessed_target_path"])}</code> — write the real target file in the notes, or choose "Not needed in target".</div>'
    if it.get("suggested_target_path"):
        path_line += f'<div>Suggested target path: <code>{esc(it["suggested_target_path"])}</code> <span class="muted">({esc(it.get("suggestion_reason"))})</span></div>'
    mapping = ""
    if m and m.get("method") not in ("same-path", "same-path(base)", None):
        cands = ", ".join(f'{esc(c["path"])}' + (f' ({c.get("similarity", c.get("matches"))})') for c in m.get("candidates", [])[:4])
        mapping = (f'<div class="mapping">Path mapping: <b>{esc(m.get("method"))}</b>, confidence <b>{esc(m.get("confidence"))}</b>'
                   f'{" — candidates: " + cands if cands else ""}{" — " + esc(m.get("note")) if m.get("note") else ""}</div>')
    signals = "".join(f"<li>{esc(s)}</li>" for s in it.get("signals", []))
    summary = ""
    if it.get("summary_lines"):
        summary = '<pre class="summary">' + esc("\n".join(it["summary_lines"])) + "</pre>"
    snippets = ""
    if any(it.get(k) for k in ("base", "source", "target")):
        snippets = f'''<div class="cols">
  <div><h5>Base (common ancestor)</h5>{code_block(it.get("base"), "del")}</div>
  <div><h5>Source — incoming</h5>{code_block(it.get("source"), "add")}</div>
  <div><h5>Target — current</h5>{code_block(it.get("target"), "chg")}</div>
</div>'''
    ai = ""
    if it.get("ai_analysis") or it.get("ai_recommendation"):
        prop = ""
        if it.get("proposed_code"):
            prop = f'<h5>Proposed merged code</h5><pre class="proposal">{esc(it["proposed_code"])}</pre>'
        rec = it.get("recommended_option")
        ai = f'''<div class="ai"><h4>AI analysis</h4><p>{esc(it.get("ai_analysis")).replace(chr(10), "<br>")}</p>
<h4>AI recommendation{(": " + esc(lab.get(rec, rec))) if rec else ""}{(" · confidence " + esc(it.get("ai_confidence"))) if it.get("ai_confidence") is not None else ""}</h4><p>{esc(it.get("ai_recommendation")).replace(chr(10), "<br>")}</p>{prop}
{("<h5>Evidence</h5><p>" + esc(it.get("ai_evidence")) + "</p>") if it.get("ai_evidence") else ""}
{("<h5>Independent check: " + esc(it.get("check_verdict")) + "</h5><p>" + esc(it.get("check_note") or "") + "</p>") if it.get("check_verdict") else ""}</div>'''
    elif it.get("needs_decision"):
        ai = '<div class="ai pending">AI review pending for this item.</div>'
    dec = ""
    if it.get("escalated"):
        dec += ('<div class="esc"><b>Needs you:</b> ' + esc("; ".join(it.get("escalation_reasons") or [])) + '</div>')
    elif it.get("decided_by") == "ai":
        dec += (f'<div class="aidec">Decided by AI: <b>{esc(lab.get(it.get("decision"), it.get("decision")))}</b> — '
                'change the option below to override (before the developer commits).</div>')
    elif it.get("decided_by") == "developer" or (it.get("decision") and it.get("needs_decision")):
        dec += f'<div class="aidec">Decided by developer: <b>{esc(lab.get(it.get("decision"), it.get("decision")))}</b></div>'
    if decision_ui:
        radios = "".join(
            f'<label class="opt{" rec" if o == it.get("recommended_option") else ""}"><input type="radio" name="d-{esc(it["id"])}" value="{o}"'
            f'{" checked" if it.get("decision") == o else ""}> {esc(lab[o])}{" ★" if o == it.get("recommended_option") else ""}</label>'
            for o in OPTIONS if not (o == "AI" and not it.get("proposed_code") and not it.get("ai_recommendation")))
        dec = f'''<div class="decision" data-id="{esc(it["id"])}"><div class="opts">{radios}</div>
<textarea placeholder="Notes for this decision (who agreed, what exactly to keep)…" data-notes="{esc(it["id"])}">{esc(it.get("decision_notes"))}</textarea></div>'''
    return f'''<section class="card sev-{esc(it["severity"])}" id="{esc(it["id"])}">
<header><span class="iid">{esc(it["id"])}</span>{badge(cat)}<span class="sev">{esc(it["severity"]).upper()}</span><span class="ttl">{esc(it["title"])}</span></header>
<div class="path">{path_line}</div>{mapping}
<div class="devs"><div><h5>Incoming (source) — who wrote these exact lines</h5>{people(it.get("source_authors"))}</div><div><h5>Current (target) — who wrote the conflicting lines</h5>{people(it.get("target_authors"))}</div></div>
{"<ul class='signals'>" + signals + "</ul>" if signals else ""}{summary}{snippets}{ai}{dec}</section>'''


CSS = """
*{box-sizing:border-box}body{font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;margin:0;background:#f4f6f8;color:#1c2430}
.wrap{max-width:1500px;margin:0 auto;padding:24px}h1{margin:0 0 4px;font-size:26px}h2{margin:32px 0 12px;font-size:20px;border-bottom:2px solid #dde3ea;padding-bottom:6px}
h4{margin:10px 0 4px}h5{margin:6px 0 4px;font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:#5b6775}
.meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:10px;background:#fff;border:1px solid #dde3ea;border-radius:10px;padding:16px;margin-top:12px}
.meta div{word-break:break-all}.meta b{display:block;font-size:11px;text-transform:uppercase;color:#5b6775;letter-spacing:.04em}
.resume{background:#102a43;color:#e3f2fd;border-radius:10px;padding:14px 16px;margin-top:12px}.resume code{color:#fff;background:#243b53;padding:2px 6px;border-radius:4px}
.tiles{display:flex;flex-wrap:wrap;gap:10px}.tile{background:#fff;border:1px solid #dde3ea;border-radius:10px;padding:10px 14px;min-width:130px}.tile .n{font-size:24px;font-weight:700}
.badge{color:#fff;font-size:11px;font-weight:700;padding:2px 8px;border-radius:10px;margin-right:8px}
.card{background:#fff;border:1px solid #dde3ea;border-left:6px solid #90a4ae;border-radius:10px;padding:14px 16px;margin:14px 0}
.card.sev-high{border-left-color:#c62828}.card.sev-medium{border-left-color:#ef6c00}.card.sev-low{border-left-color:#607d8b}
.card header{display:flex;align-items:center;flex-wrap:wrap;gap:6px;margin-bottom:6px}.iid{font-weight:800;margin-right:6px}.sev{font-size:11px;font-weight:700;color:#5b6775;margin-right:8px}.ttl{font-weight:600}
.path code,.mapping code{background:#eef2f6;padding:1px 5px;border-radius:4px}.mapping{font-size:13px;color:#37474f;margin-top:4px}
.devs{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:8px 0;font-size:13px}.dev code{background:#eef2f6;padding:0 4px;border-radius:3px}
.muted{color:#78909c}.warn{color:#c62828}.signals{margin:6px 0;padding-left:20px;color:#8d4b00}
.cols{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px}.cols>div{min-width:0}
table.code{width:100%;border-collapse:collapse;font:12px/1.45 SFMono-Regular,Menlo,Consolas,monospace;background:#fbfcfd;border:1px solid #e3e8ee;border-radius:6px;display:block;overflow-x:auto}
table.code td{padding:0 6px;white-space:pre;vertical-align:top}td.ln{color:#90a4ae;text-align:right;user-select:none;border-right:1px solid #e3e8ee;min-width:38px}
td.who{color:#6a4fb3;font:10px/1.45 -apple-system,Segoe UI,sans-serif;max-width:90px;overflow:hidden;text-overflow:ellipsis;border-right:1px solid #e3e8ee}
.lines{background:#ede7f6;color:#4527a0;border-radius:4px;padding:0 5px;font:12px SFMono-Regular,Menlo,monospace}
tr.add td.lc{background:#e6f4ea}tr.del td.lc{background:#fdecea}tr.chg td.lc{background:#fff4e0}.code.empty{padding:10px;color:#90a4ae;border:1px dashed #cfd8dc;border-radius:6px;font-size:12px}
pre.summary,pre.proposal{background:#0f1720;color:#e6edf3;padding:10px 12px;border-radius:8px;overflow:auto;font:12px/1.45 SFMono-Regular,Menlo,Consolas,monospace}
.esc{background:#fdecea;border:1px solid #f5c2c0;border-radius:8px;padding:8px 12px;margin-top:10px}
.aidec{background:#e8f5e9;border:1px solid #c8e6c9;border-radius:8px;padding:8px 12px;margin-top:10px}
.ai{background:#f3f0ff;border:1px solid #d9d0ff;border-radius:8px;padding:6px 12px;margin-top:10px}.ai.pending{background:#fff8e1;border-color:#ffe082}
.decision{margin-top:10px;background:#f7fafc;border:1px solid #dde3ea;border-radius:8px;padding:10px}.opts{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:8px}
.opt{border:1px solid #cfd8dc;border-radius:16px;padding:3px 10px;cursor:pointer;background:#fff}.opt.rec{border-color:#7e57c2}.opt input{margin-right:4px}
textarea{width:100%;min-height:48px;border:1px solid #cfd8dc;border-radius:6px;padding:6px;font:inherit}
table.list{width:100%;border-collapse:collapse;background:#fff;font-size:13px}table.list th,table.list td{border-bottom:1px solid #e3e8ee;padding:5px 8px;text-align:left;vertical-align:top}
table.list th{background:#eef2f6}details{background:#fff;border:1px solid #dde3ea;border-radius:10px;padding:8px 14px;margin:10px 0}summary{cursor:pointer;font-weight:600}
.bar{position:sticky;top:0;z-index:5;background:#ffffffee;backdrop-filter:blur(4px);border-bottom:1px solid #dde3ea;padding:8px 24px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.bar button{background:#1565c0;color:#fff;border:0;border-radius:6px;padding:7px 12px;font-weight:600;cursor:pointer}.bar input{border:1px solid #cfd8dc;border-radius:6px;padding:6px}
#progress{font-weight:600}nav a{margin-right:12px}
@media print{.bar{display:none}.card{break-inside:avoid}}
@media (max-width:1000px){.cols,.devs{grid-template-columns:1fr}}
"""

JS = """
const RID = %(rid)s; const KEY = 'merge-report-' + RID;
function collect(){const d={};document.querySelectorAll('.decision').forEach(el=>{const id=el.dataset.id;
 const r=el.querySelector('input[type=radio]:checked');const n=el.querySelector('textarea').value.trim();
 if(r||n)d[id]={choice:r?r.value:null,notes:n};});return d;}
function save(){try{localStorage.setItem(KEY,JSON.stringify({by:document.getElementById('by').value,d:collect()}));}catch(e){} progress();}
function load(){try{const s=JSON.parse(localStorage.getItem(KEY)||'null');if(!s)return;document.getElementById('by').value=s.by||'';
 for(const[id,v]of Object.entries(s.d||{})){if(v.choice){const r=document.querySelector(`input[name="d-${id}"][value="${v.choice}"]`);if(r)r.checked=true;}
 const t=document.querySelector(`textarea[data-notes="${id}"]`);if(t&&v.notes)t.value=v.notes;}}catch(e){}}
function progress(){const need=[...document.querySelectorAll('.need .decision')];const done=need.filter(el=>el.querySelector('input:checked')).length;
 document.getElementById('progress').textContent=`${done} / ${need.length} required decisions made`;}
function exportJson(){const out={report_id:RID,exported_at:new Date().toISOString(),decided_by:document.getElementById('by').value,decisions:collect()};
 const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(out,null,2)],{type:'application/json'}));
 a.download='decisions-'+RID+'.json';a.click();}
function copyResume(){const t=document.getElementById('resumecmd').textContent;navigator.clipboard&&navigator.clipboard.writeText(t);}
document.addEventListener('change',save);document.addEventListener('input',e=>{if(e.target.tagName==='TEXTAREA'||e.target.id==='by')save();});
window.addEventListener('load',()=>{load();progress();});
"""


def main():
    path = sys.argv[1]
    d = json.load(open(path))
    folder = os.path.dirname(os.path.abspath(path))
    rid = d["report_id"]
    items = d["items"]
    need_all = sorted([i for i in items if i["needs_decision"]], key=lambda i: (SEV_ORDER.get(i["severity"], 9), i["file"]))
    need = [i for i in need_all if not i.get("decision")]                       # escalated / still open
    ai_decided = [i for i in need_all if i.get("decision") and i.get("decided_by") == "ai"]
    dev_decided = [i for i in need_all if i.get("decision") and i.get("decided_by") != "ai"]
    review = sorted([i for i in items if not i["needs_decision"] and (i.get("ai_category") or i["category"]) in
                     ("NEAR_CHANGE", "RESTRUCTURED", "OPTIMIZED_IN_TARGET", "OPTIMIZED_IN_SOURCE", "NEW_FILE", "BINARY", "PROJECT_FILE",
                      "VENDORED_BUNDLE", "MAPPING_UNCERTAIN", "NEW_SYMBOL", "SYMBOL_NOT_FOUND")],
                    key=lambda i: i["file"])
    review_ids = {i["id"] for i in review} | {i["id"] for i in need}
    auto = [i for i in items if i["id"] not in review_ids]
    missing_ai = [i["id"] for i in need_all if not (i.get("ai_analysis") and i.get("ai_recommendation"))]
    g, s, t = d["generator"], d["source"], d["target"]
    resume_cmd = f'Resume merge report {rid} — decisions: {folder}/decisions-{rid}.json'

    st_ = d.get("structure") or {}
    structure_html = ""
    if st_:
        rows = "".join(f'<tr><td><code>{esc(v["source_dir"] or "/")}</code></td><td>→</td><td><code>{esc(v["target_dir"] or "(not in target)")}</code></td>'
                       f'<td>{esc(v["votes"])}{" ✔ confirmed" if v.get("confirmed") else ""}</td><td>{esc(v["used_by"])}</td></tr>' for v in st_.get("folder_map", []))
        structure_html = (f'<h2>Folder structure — {"DIFFERENT" if st_.get("restructured") else "same"}</h2>'
            f'<p><b>Merge strategy: {esc(st_.get("strategy"))}</b> — {esc(st_.get("why"))}. '
            f'Moved files: {esc(st_.get("moved_files"))} · files to confirm: {esc(st_.get("uncertain_files"))} · '
            f'missing in target: {esc(st_.get("missing_in_target"))}</p>'
            + (f'<table class="list"><tr><th>Source folder</th><th></th><th>Target folder</th><th>Evidence (files)</th><th>Used for</th></tr>{rows}</table>'
               '<p class="muted">Wrong row? Tell the agent; it is written to path-map.json and the analysis is re-run.</p>' if rows else ""))
        fm_path = os.path.join(folder, "file-map.json")
        if os.path.exists(fm_path):
            fm = json.load(open(fm_path))
            frows = []
            for src, e in sorted((fm.get("files") or {}).items(), key=lambda kv: (not kv[1].get("needs_developer"), kv[0])):
                tgt = e.get("target") or (e.get("placement") or {}).get("path") or "—"
                sy = "".join(f'<div class="muted">· {esc(q)} → {esc((x or {}).get("target") if isinstance(x, dict) else x)}</div>'
                             for q, x in (e.get("symbols") or {}).items())
                frows.append(f'<tr><td><code>{esc(src)}</code></td><td>{esc(e.get("status"))}</td><td><code>{esc(tgt)}</code>{sy}</td>'
                             f'<td>{esc(e.get("confidence"))}</td><td>{esc(e.get("decided_by"))}</td>'
                             f'<td>{"<b class=warn>confirm</b>" if e.get("needs_developer") else "✔"}</td><td>{esc(e.get("note") or "; ".join(e.get("evidence") or []))}</td></tr>')
            structure_html += (f'<h3>File map ({len(frows)} files — built by AI, rows marked "confirm" need a developer)</h3>'
                               '<table class="list"><tr><th>Source file</th><th>Status</th><th>Target (per function if split)</th><th>Conf.</th>'
                               '<th>Decided by</th><th></th><th>Evidence / AI note</th></tr>' + "".join(frows) + '</table>')
        ign = d.get("ignored_files") or []
        if ign:
            structure_html += (f'<details><summary>Ignored as noise ({len(ign)}) — user state, DerivedData, .DS_Store …</summary><ul>'
                               + "".join(f'<li><code>{esc(x["path"])}</code></li>' for x in ign[:200]) + '</ul></details>')
    tiles = "".join(f'<div class="tile"><div class="n">{n}</div>{badge(c)}<div class="muted" style="font-size:12px">{esc(CAT_INFO.get(c, ("", ""))[1])}</div></div>'
                    for c, n in sorted(d["summary"]["by_category"].items(), key=lambda kv: -kv[1]))
    def who(lst):
        return "".join(f'<div><b>{esc(p.get("name"))}</b> <span class="lines">{esc(ranges(p.get("line_numbers")) or "base " + ranges(p.get("base_line_numbers")))}</span> '
                       f'<span class="muted">{esc(p.get("role", ""))} · {esc((p.get("date") or "")[:10])} · {esc(p.get("short"))}</span>'
                       + (f'<div class="muted">↳ originally {esc(p["ported_from"]["name"])} ({esc(p["ported_from"]["short"])})</div>' if p.get("ported_from") else "")
                       + '</div>' for p in lst) or '<span class="muted">—</span>'
    talk = "".join(f'<tr><td><a href="#{esc(i["id"])}">{esc(i["id"])}</a></td><td>{badge(i.get("ai_category") or i["category"])}</td>'
                   f'<td><code>{esc(i.get("target_path") or i["file"])}</code></td><td>{who(i.get("source_authors", []))}</td>'
                   f'<td>{who(i.get("target_authors", []))}</td></tr>' for i in need_all)
    owners = {}
    for i in need_all:
        for side, key in (("incoming", "source_authors"), ("current", "target_authors")):
            for p in i.get(key, []):
                o = owners.setdefault(p.get("name"), {"email": p.get("email"), "ids": []})
                o["ids"].append(f'{i["id"]} ({side})')
    devs = "".join(f'<tr><td><b>{esc(n)}</b></td><td>{esc(v["email"])}</td><td>{esc(", ".join(dict.fromkeys(v["ids"])))}</td></tr>'
                   for n, v in sorted(owners.items(), key=lambda kv: -len(kv[1]["ids"])))
    commits = "".join(f'<tr><td><code>{esc(c["short"])}</code></td><td>{esc(c["date"])}</td><td>{esc(c["name"])}</td><td>{esc(c["subject"])}</td>'
                      f'<td>{"✔ equivalent already in target" if c.get("already_in_target") else ""}</td></tr>' for c in d["commits"])
    auto_rows = "".join(f'<tr><td><a href="#{esc(i["id"])}">{esc(i["id"])}</a></td><td>{badge(i["category"])}</td><td><code>{esc(i["file"])}</code>'
                        f'{(" → <code>" + esc(i["target_path"]) + "</code>") if i.get("target_path") and i["target_path"] != i["file"] else ""}</td>'
                        f'<td>{esc((i.get("source") or {}).get("start", ""))}</td><td>{esc(", ".join(a.get("name", "") + " " + a.get("date", "") for a in i.get("source_authors", [])[:2]))}</td></tr>'
                        for i in auto)
    paths = "".join(f'<tr><td><code>{esc(f["source_path"])}</code></td><td>{esc(f["source_status"])}</td><td><code>{esc(f["target_path"] or "— not found —")}</code></td>'
                    f'<td>{esc(f["mapping"]["method"])}</td><td>{esc(f["mapping"]["confidence"])}</td><td>{"🔒" if f["protected"] else ""}</td></tr>'
                    for f in d["files"])
    tgt_only = "".join(f'<tr><td>{esc(x["status"])}</td><td><code>{esc(x["path"])}</code></td></tr>' for x in d.get("target_only_changes", [])[:400])

    page = f'''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Merge report {esc(s["branch"])} → {esc(t["branch"])} · {esc(rid)}</title><style>{CSS}</style></head><body>
<div class="bar"><b>{esc(rid)}</b><span id="progress"></span><input id="by" placeholder="Decided by (your name)"><button onclick="exportJson()">Export decisions (.json)</button>
<button onclick="window.print()" style="background:#455a64">Print / PDF</button><nav><a href="#decide">Decisions</a><a href="#review">Review</a><a href="#auto">Auto-applied</a><a href="#paths">Path map</a><a href="#commits">Commits</a></nav></div>
<div class="wrap">
<h1>Merge report: <code>{esc(s["branch"])}</code> → <code>{esc(t["branch"])}</code></h1>
<div class="muted">Status: <b>{esc(d.get("status"))}</b> · generated {esc(d["generated_at"])} · nothing has been merged yet — this report is for discussion.</div>
<div class="meta">
<div><b>Report ID</b>{esc(rid)}</div>
<div><b>Generated by</b>{esc(g.get("tool"))}</div>
<div><b>Chat / session id</b>{esc(g.get("session_id") or "not available — see resume line")}</div>
<div><b>Source (merge FROM)</b>{esc(s["branch"])} @ {esc(s["head"][:12])}<br>{esc(s["folder"])}</div>
<div><b>Target (merge INTO)</b>{esc(t["branch"])} @ {esc(t["head"][:12])}<br>{esc(t["folder"])}</div>
<div><b>History</b>{esc(d["mode"])} · base {esc((d["analysis_base"] or "")[:12])} ({esc(d["base_note"])})</div>
<div><b>Report folder</b>{esc(folder)}</div>
<div><b>Protected paths</b>{esc(", ".join(d["protected_globs"]))}</div>
</div>
<div class="resume"><b>How to continue.</b> 1) Each developer picks a decision on every card under “Decisions needed” (★ = AI recommendation) and adds notes.
2) Click <b>Export decisions</b> and save the file into the report folder (or edit <code>report.md</code> checkboxes). 3) In the same chat{(" (" + esc(g.get("session_id")) + ")") if g.get("session_id") else ""}, or any new chat with this skill, say:<br>
<code id="resumecmd">{esc(resume_cmd)}</code> <button onclick="copyResume()" style="margin-left:8px">Copy</button>
{("<br>Resume hint: <code>" + esc(g.get("resume_hint")) + "</code>") if g.get("resume_hint") else ""}</div>

<details open><summary>How to read a card</summary><ul>
<li><b>Base (common ancestor)</b> — the code as it was at the last commit both branches share (<code>{esc((d["analysis_base"] or "")[:12])}</code>), i.e. before either branch changed it. Red lines = what was there and got changed.</li>
<li><b>Source — incoming</b> — the same code on <code>{esc(s["branch"])}</code> now (what the merge brings). Green = changed by source.</li>
<li><b>Target — current</b> — the same code on <code>{esc(t["branch"])}</code> now (what you have). Amber = changed by target.</li>
<li>The purple name next to a line is the developer who wrote that exact line (on Base: who removed it). The "Who to talk to" table lists only those people.</li>
<li>Comparing Source and Target with Base shows who changed what: if only one side differs from Base, take that side; if both differ, a person decides.</li></ul></details>
{structure_html}
<h2>Summary</h2>
<div class="tiles"><div class="tile"><div class="n">{d["summary"]["needs_decision"]}</div>decisions needed</div>
<div class="tile"><div class="n">{d["summary"]["items"]}</div>change items</div><div class="tile"><div class="n">{d["summary"]["source_commits"]}</div>source commits</div>
<div class="tile"><div class="n">{d["summary"]["files_changed_in_source"]}</div>files changed in source</div>{tiles}</div>
{"<p class='warn'><b>Warning:</b> AI review missing for " + ", ".join(missing_ai) + "</p>" if missing_ai else ""}
<h3>Who to talk to — exact authors of the conflicting lines</h3>
<p class="muted">Only the developers who wrote (or removed) the exact lines in each decision item — taken line by line from git blame, not from who else touched the file.</p>
<table class="list"><tr><th>Item</th><th>Type</th><th>File</th><th>Incoming lines written by</th><th>Current lines written by</th></tr>{talk or '<tr><td colspan="5">No decisions needed.</td></tr>'}</table>
<h3>Per developer</h3><table class="list"><tr><th>Developer</th><th>Email</th><th>Decision items (side)</th></tr>{devs or '<tr><td colspan="3">—</td></tr>'}</table>

<h2 id="decide">Needs you ({len(need)})</h2><div class="need">{"".join(item_card(i) for i in need) or "<p>Nothing — the AI decided every item from the code; see below. Override any card before the commit if you disagree.</p>"}</div>
{("<h2 id='aidecided'>Decided by AI (" + str(len(ai_decided)) + ")</h2><p class='muted'>Each was reviewed from the code logic, with evidence and (for high-severity items) an independent second check. Change any option to override.</p><details><summary>Show " + str(len(ai_decided)) + " AI decisions</summary><div class='need'>" + "".join(item_card(i) for i in ai_decided) + "</div></details>") if ai_decided else ""}
{("<h2>Decided by developer (" + str(len(dev_decided)) + ")</h2><div class='need'>" + "".join(item_card(i) for i in dev_decided) + "</div>") if dev_decided else ""}
<h2 id="review">Review — merges, but check the logic ({len(review)})</h2>
<p class="muted">These do not block the merge. Pick a decision only if you disagree with the default (take source).</p>
<div class="review">{"".join(item_card(i) for i in review) or "<p>None.</p>"}</div>
<h2 id="auto">Auto-applied changes ({len(auto)})</h2>
<p class="muted">Every remaining source change, listed so nothing is merged unseen. Flag any by adding it to the notes of a decision or telling the merge owner.</p>
<details><summary>Show all {len(auto)} items</summary><table class="list"><tr><th>ID</th><th>Category</th><th>File</th><th>Line</th><th>Author</th></tr>{auto_rows}</table>
{"".join(item_card(i, decision_ui=False) for i in auto)}</details>
<h2 id="paths">File / path map ({len(d["files"])})</h2><details><summary>Show</summary><table class="list"><tr><th>Source path</th><th>Status</th><th>Target path</th><th>Method</th><th>Confidence</th><th>Protected</th></tr>{paths}</table></details>
<h2 id="commits">Source commits ({len(d["commits"])})</h2><details><summary>Show</summary><table class="list"><tr><th>Commit</th><th>Date</th><th>Author</th><th>Subject</th><th></th></tr>{commits}</table></details>
<h2>Changed only in target ({len(d.get("target_only_changes", []))})</h2><details><summary>Show</summary><p class="muted">Not touched by the merge; listed for context.</p><table class="list">{tgt_only}</table></details>
<p class="muted" style="margin-top:30px">Generated by the safe-branch-merge skill · {esc(rid)}</p>
</div><script>{JS % {"rid": json.dumps(rid)}}</script></body></html>'''
    with open(os.path.join(folder, "report.html"), "w") as f:
        f.write(page)

    # ---------------- Markdown twin
    md = [f"# Merge report: `{s['branch']}` → `{t['branch']}`", "",
          f"| | |", "|---|---|", f"| Report ID | {rid} |", f"| Status | {d.get('status')} |",
          f"| Generated | {d['generated_at']} by {g.get('tool')} |", f"| Chat / session id | {g.get('session_id') or 'n/a'} |",
          f"| Source (FROM) | `{s['branch']}` @ {s['head'][:12]} — `{s['folder']}` |", f"| Target (INTO) | `{t['branch']}` @ {t['head'][:12]} — `{t['folder']}` |",
          f"| History | {d['mode']}, base {(d['analysis_base'] or '')[:12]} ({d['base_note']}) |", "",
          f"**To resume:** tick one box per item below (or use report.html → Export decisions), then say: `{resume_cmd}`", "",
          f"Decided by: ______", ""]
    if st_:
        md += [f"## Folder structure — {'DIFFERENT' if st_.get('restructured') else 'same'}", "",
               f"**Merge strategy: {st_.get('strategy')}** — {st_.get('why')}", ""]
        for v in st_.get("folder_map", []):
            md.append(f"- `{v['source_dir'] or '/'}` → `{v['target_dir'] or '(not in target)'}` ({v['votes']} files, used for {v['used_by']})")
        md.append("")
    md += ["## Summary", ""]
    for c, n in sorted(d["summary"]["by_category"].items(), key=lambda kv: -kv[1]):
        md.append(f"- **{c}**: {n} — {CAT_INFO.get(c, ('', ''))[1]}")

    def md_snip(title, snip):
        if not snip:
            return [f"*{title}: not present*", ""]
        out = [f"*{title}* (from line {snip['start']}; `»` = changed)", "```"]
        mk = set(snip.get("marked", []))
        ow = snip.get("authors") or {}
        wid = max([len(v) for v in ow.values()] + [0])
        for i, l in enumerate(snip["lines"]):
            who = (ow.get(str(i), "")[:18]).ljust(min(wid, 18)) + " " if wid else ""
            out.append(f"{'»' if i in mk else ' '} {snip['start'] + i:5d} {who}| {l}")
        return out + ["```", ""]

    def md_item(it, with_dec=True):
        cat = it.get("ai_category") or it["category"]
        lab = labels_for(cat)
        out = [f"### {it['id']} · {cat} · {it['severity'].upper()} — {it['title']}", "",
               f"- File: `{it['file']}`" + (f" → `{it['target_path']}`" if it.get("target_path") and it["target_path"] != it["file"] else "")]
        m = it.get("mapping") or {}
        if m.get("method") not in ("same-path", "same-path(base)", None):
            out.append(f"- Path mapping: {m.get('method')} (confidence {m.get('confidence')})")
        if it.get("guessed_target_path"):
            out.append(f"- ⚠ Unconfirmed guess (NOT compared): `{it['guessed_target_path']}` — name the real target file in Notes")
        if it.get("suggested_target_path"):
            out.append(f"- Suggested target path: `{it['suggested_target_path']}` ({it.get('suggestion_reason')})")
        for side, label in (("source", "Incoming lines by"), ("target", "Current lines by")):
            for p in it.get(f"{side}_authors", [])[:6]:
                ln = (f" {ranges(p.get('line_numbers'))}" if p.get("line_numbers") else "") + \
                     (f" (removed base {ranges(p.get('base_line_numbers'))})" if p.get("base_line_numbers") else "") + \
                     (f" (committed by {p['committer']})" if p.get("committer") else "")
                port = f" (ported from {p['ported_from']['short']} by {p['ported_from']['name']})" if p.get("ported_from") else ""
                out.append(f"- {label}: **{p.get('name')}** <{p.get('email')}> — {p.get('role', '')}{ln} — {p.get('date')} — `{p.get('short')}` {p.get('subject')}{port}")
        for sg in it.get("signals", []):
            out.append(f"- ⚠ {sg}")
        out.append("")
        if it.get("summary_lines"):
            out += ["```"] + it["summary_lines"] + ["```", ""]
        out += md_snip("Base", it.get("base")) if it.get("base") else []
        out += md_snip("Source — incoming", it.get("source")) if it.get("source") else []
        out += md_snip("Target — current", it.get("target")) if it.get("target") or it.get("base") else []
        if it.get("ai_analysis"):
            out += [f"**AI analysis:** {it['ai_analysis']}", ""]
        if it.get("escalated"):
            out += [f"**Needs you:** {'; '.join(it.get('escalation_reasons') or [])}", ""]
        if it.get("ai_evidence"):
            out += [f"**Evidence:** {it['ai_evidence']}", ""]
        if it.get("check_verdict"):
            out += [f"**Independent check:** {it['check_verdict']} — {it.get('check_note') or ''}", ""]
        if it.get("ai_recommendation"):
            rec = it.get("recommended_option")
            out += [f"**AI recommendation{(' (' + lab.get(rec, rec) + ')') if rec else ''}:** {it['ai_recommendation']}", ""]
        if it.get("proposed_code"):
            out += [f"```{it.get('proposed_language') or ''}", it["proposed_code"], "```", ""]
        if with_dec:
            boxes = "  ".join(f"[{'x' if it.get('decision') == o else ' '}] {o} ({lab[o]})" for o in OPTIONS)
            out += [f"**Decision:** {boxes}", "", f"**Notes:** {it.get('decision_notes') or ''}", "", "---", ""]
        return out

    md += ["", f"## Needs you ({len(need)})", ""]
    for it in need:
        md += md_item(it)
    if ai_decided:
        md += [f"## Decided by AI ({len(ai_decided)}) — change the ticked box to override", ""]
        for it in ai_decided:
            md += md_item(it)
    if dev_decided:
        md += [f"## Decided by developer ({len(dev_decided)})", ""]
        for it in dev_decided:
            md += md_item(it)
    md += [f"## Review — merges, but check the logic ({len(review)})", ""]
    for it in review:
        md += md_item(it)
    md += [f"## Auto-applied changes ({len(auto)})", "", "| ID | Category | File | Line | Author |", "|---|---|---|---|---|"]
    for i in auto:
        md.append(f"| {i['id']} | {i['category']} | `{i['file']}` | {(i.get('source') or {}).get('start', '')} | "
                  f"{', '.join(a.get('name', '') + ' ' + a.get('date', '') for a in i.get('source_authors', [])[:2])} |")
    md += ["", f"## Source commits ({len(d['commits'])})", ""]
    for c in d["commits"]:
        md.append(f"- `{c['short']}` {c['date']} **{c['name']}** — {c['subject']}" + (" *(equivalent already in target)*" if c.get("already_in_target") else ""))
    with open(os.path.join(folder, "report.md"), "w") as f:
        f.write("\n".join(md) + "\n")

    print(f"written: {os.path.join(folder, 'report.html')}")
    print(f"written: {os.path.join(folder, 'report.md')}")
    print(f"needs developer: {len(need)}  decided by AI: {len(ai_decided)}  by developer: {len(dev_decided)}  review: {len(review)}  auto: {len(auto)}")
    if missing_ai:
        print("WARNING: AI analysis/recommendation missing for: " + ", ".join(missing_ai))
        sys.exit(3)


if __name__ == "__main__":
    main()
