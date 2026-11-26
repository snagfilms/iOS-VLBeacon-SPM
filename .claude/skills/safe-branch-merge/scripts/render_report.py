#!/usr/bin/env python3
"""
render_report.py — turn analysis.json into the developer discussion report.

Writes, next to analysis.json:
  report.html   self-contained page: decision cards, side-by-side snippets, AI recommendation,
                per-item decision + notes, "Export decisions" button (downloads decisions-<ID>.json),
                review tracker (reviewed / pending per card and per developer, "Mark reviewed"),
                ready-to-merge gate, developer filter + copyable pending list, multi-file import with
                reviewer-disagreement detection, and persistence (browser storage + Chrome/Edge auto-save file)
  report.md     the same content in Markdown with [ ] checkboxes developers can tick by hand

Usage: render_report.py <report_folder>/analysis.json
"""
import glob, html, json, os, re, sys, datetime

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
    "GENERATED":         ("#78909c", "Generated code — kept as target; run the generator after the merge instead of merging output."),
    "TOOLING":           ("#8d6e63", "AI-agent / editor configuration (.cursor, .claude, AGENTS.md …) — not product code."),
    "JUNK":              ("#b0bec5", "Per-user / OS file (.DS_Store, xcuserdata) — kept as target."),
    "IB_METADATA":       ("#b0bec5", "Interface Builder metadata only (client module name with provider=target, tool version) — kept as target."),
}
SEV_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}
OPTIONS = ["SOURCE", "TARGET", "BOTH", "AI", "CUSTOM"]
DEFAULT_LABELS = {"SOURCE": "Replace with source code as-is", "TARGET": "Keep target code as-is (source change dropped)",
                  "BOTH": "Keep both behaviours", "AI": "Source behaviour inside target code (AI proposal)",
                  "CUSTOM": "Custom — see notes"}
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


QUAL = {}      # quality.json (quality_scan.py), loaded in main()
BATCH = {}     # item id -> review batch name (review-queue/*.results.json)
EV_STOP = {"source", "target", "base", "self", "return", "guard", "true", "false", "func", "with", "that", "this", "from", "only",
           "when", "into", "both", "keep", "take", "line", "lines", "code", "same", "change", "changes", "commit", "Source", "Target"}


def evidence_terms(it):
    """Identifiers and file:line references named in the AI's evidence / recommendation / check note."""
    txt = " ".join(str(it.get(k) or "") for k in ("ai_evidence", "ai_recommendation", "check_note"))
    terms = set()
    for chunk in re.findall(r"`([^`]+)`", txt):
        terms |= {w for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]{4,}", chunk) if w not in EV_STOP}
    terms |= {w for w in re.findall(r"\b[a-z]+[A-Z][A-Za-z0-9_]{2,}\b|\b[A-Z][a-z]+[A-Z][A-Za-z0-9_]{2,}\b", txt) if w not in EV_STOP}
    lines = {int(n) for n in re.findall(r"\.(?:swift|m|mm|h|kt|java):~?(\d+)", txt)}
    return terms, lines


def code_block(snip, cls, terms=None, lines=None, anchor=None):
    if not snip:
        return '<div class="code empty">— not present —</div>'
    marked = set(snip.get("marked", []))
    owners = snip.get("authors") or {}
    rows = []
    pat = re.compile(r"\b(" + "|".join(sorted(map(re.escape, terms), key=len, reverse=True)) + r")\b") if terms else None
    for i, line in enumerate(snip.get("lines", [])):
        who = owners.get(str(i), "")
        n = snip["start"] + i
        ev = (pat and pat.search(line) and i in marked) or (lines and n in lines)
        c = " ".join(x for x in (cls if i in marked else "", "ev" if ev else "") if x)
        rid = f' id="{esc(anchor)}-L{n}"' if anchor and ev else ""
        rows.append(f'<tr class="{c}"{rid}><td class="ln">{n}</td>'
                    f'<td class="who" title="{esc(who)}">{esc(who)}</td><td class="lc">{esc(line) or "&nbsp;"}</td></tr>')
    return f'<table class="code">{"".join(rows)}</table>'


def ev_hits(it, terms, lines):
    """[(side label, anchor, line)] for the evidence rows marked in code_block."""
    out = []
    pat = re.compile(r"\b(" + "|".join(sorted(map(re.escape, terms), key=len, reverse=True)) + r")\b") if terms else None
    for side, lab in (("source", "S"), ("target", "T"), ("base", "B")):
        snip = it.get(side) or {}
        mk = set(snip.get("marked", []))
        for i, line in enumerate(snip.get("lines", [])):
            n = snip["start"] + i
            if (pat and pat.search(line) and i in mk) or n in lines:
                out.append((lab, f'{it["id"]}-{side}-L{n}', n))
    return out


def quality_chips(it):
    q = (QUAL.get("items") or {}).get(it["id"]) or {}
    fq = (QUAL.get("files") or {}).get(it.get("target_path") or it["file"]) or {}
    out = []
    for p in q.get("platform") or []:
        out.append(f'<span class="plat" title="Platform context of the changed lines">{esc(p)}</span>')
    if fq:
        out.append(f'<a class="qchip lv-{esc(fq["level"])}" href="#quality" title="File risk {fq["score"]}/100: {fq["commits"]} commits / '
                   f'{fq["authors"]} authors in {fq["days"]} days · tests: {esc(fq["tested"] or "none")} · sensitive area: {esc(fq["sensitive"])}">'
                   f'File risk {fq["score"]}</a>')
    if QUAL:
        t = q.get("tests") or []
        fn = [x for x in t if x["kind"] == "function"]
        if fn:
            out.append('<span class="qchip ok" title="' + esc("; ".join(x["file"] + " (" + ", ".join(x["names"]) + ")" for x in fn)) + f'">✓ tests call this ({len(fn)})</span>')
        elif t:
            out.append('<span class="qchip warn" title="' + esc("; ".join(x["file"] for x in t)) + '">tests only reference the type</span>')
        else:
            out.append('<span class="qchip bad" title="No test file references the changed function or its type">no tests</span>')
        lt = q.get("lint") or []
        if lt:
            out.append('<span class="qchip bad" title="' + esc("; ".join(f'L{v["line"]} {v["rule"]}: {v["reason"]}' for v in lt)) + f'">{len(lt)} new lint on merged lines</span>')
    if BATCH.get(it["id"]):
        out.append(f'<span class="batch" title="Review batch">{esc(BATCH[it["id"]])}</span>')
    return ('<div class="qrow">' + "".join(out) + "</div>") if out else ""


def area_of(it):
    q = (QUAL.get("items") or {}).get(it["id"]) or {}
    if q.get("area"):
        return q["area"]
    parts = [p for p in os.path.dirname(it.get("target_path") or it["file"]).split("/") if p]
    return parts[-1] if parts else "(root)"


def qual_tokens(it):
    q = (QUAL.get("items") or {}).get(it["id"]) or {}
    fq = (QUAL.get("files") or {}).get(it.get("target_path") or it["file"]) or {}
    t = []
    if fq.get("level") == "high":
        t.append("q-filehigh")
    if QUAL and not any(x["kind"] == "function" for x in q.get("tests") or []):
        t.append("q-notests")
    if q.get("lint"):
        t.append("q-lint")
    if q.get("platform"):
        t.append("q-platform")
    return t


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


DROP_CATS = {"CONFLICT", "SYMBOL_NOT_FOUND", "DELETED_IN_TARGET", "MAPPING_UNCERTAIN", "OPTIMIZED_IN_TARGET",
             "OPTIMIZED_IN_SOURCE", "NEW_SYMBOL", "NEW_FILE", "RESTRUCTURED", "NEAR_CHANGE", "PROJECT_FILE"}
QUAL_LABELS = {"q-filehigh": "high-risk file", "q-notests": "no test calls it", "q-lint": "new lint on merged lines", "q-platform": "platform-specific (#if os / tvOS)"}
RISK_LABELS = {"lowconf": "low confidence", "drops": "drops source code", "weakcheck": "weak second check",
               "doubt": "earlier doubt cleared", "lookalike": "look-alike in parallel module", "deps": "depends on other cards",
               "recheck": "AI re-check pending", "reverted": "target reverted this", "secret": "possible secret"}


def risks_of(it):
    cat = it.get("ai_category") or it["category"]
    r = []
    c = it.get("ai_confidence")
    if c is not None and c < 0.85 and it.get("recommended_option"):
        r.append("lowconf")
    if (it.get("decision") or it.get("recommended_option")) == "TARGET" and cat in DROP_CATS:
        r.append("drops")
    note = (it.get("check_note") or "").strip()
    if it.get("recommended_option") and it.get("check_by") != "rule" and (len(note) < 30 or re.search(
            r"^(agree[sd]?|ok|lgtm)\W*$|adopted (the )?agent|second pass settled", note, re.I)):
        r.append("weakcheck")
    if it.get("doubt_cleared") and it.get("decided_by") != "developer":
        r.append("doubt")
    if it.get("counterparts"):
        r.append("lookalike")
    if it.get("depends_on"):
        r.append("deps")
    if it.get("recheck"):
        r.append("recheck")
    if it.get("reverted_in_target"):
        r.append("reverted")
    if it.get("secret"):
        r.append("secret")
    return r


def extras(it):
    out = ""
    rk = risks_of(it)
    if rk:
        out += '<div class="risks">' + "".join(f'<span class="risk r-{k}">{esc(RISK_LABELS[k])}</span>' for k in rk) + "</div>"
    if it.get("recheck"):
        out += '<div class="esc"><b>AI re-check pending:</b> ' + esc("; ".join(it["recheck"])) + "</div>"
    if it.get("doubt_cleared") and it.get("decided_by") != "developer":     # a person decided: the old doubt is settled
        out += (f'<div class="esc"><b>Earlier doubt cleared:</b> an earlier review said <b>{esc(it["doubt_cleared"])}</b>. '
                f'Reason given: {esc(it.get("change_reason") or "none")}</div>')
    if it.get("depends_on"):
        out += ('<div class="deps">Depends on: ' + " ".join(f'<a href="#{esc(x)}" class="dep">{esc(x)}</a>' for x in it["depends_on"])
                + ' <span class="muted">— if one of these changes, review this card again</span></div>')
    if it.get("counterparts"):
        v = it.get("counterpart_verdict")
        rows = "".join(f'<li><code>{esc(c["path"])}</code>' + (f' — <span class="warn">does not use {esc(", ".join(c["missing"]))}</span>' if c.get("missing") else "")
                       + (f' — uses {esc(", ".join(c["uses"]))}' if c.get("uses") else "") + "</li>" for c in it["counterparts"])
        out += (f'<div class="cp"><b>Look-alike in a parallel module</b> — the same screen/service also exists here; '
                f'the source change may need porting too.<ul>{rows}</ul>'
                + (f'<b>Verdict: {esc(v)}</b> — {esc(it.get("counterpart_note") or "")}' if v else '<b class="warn">Not checked yet.</b>') + "</div>")
    h = it.get("ai_history") or []
    if len(h) > 1:
        rows = "".join(f'<tr><td>{esc((x.get("at") or "")[:16].replace("T", " "))}</td><td>{esc(x.get("source"))}{(" · " + esc(x["by"])) if x.get("by") else ""}</td>'
                       f'<td>{esc(x.get("recommended_option"))}</td><td>{esc(x.get("ai_confidence"))}</td><td>{"⚠ escalated" if x.get("escalate") else ""}</td>'
                       f'<td>{esc(x.get("check_verdict"))}</td><td>{esc(x.get("change_reason") or "")}</td></tr>' for x in h)
        out += (f'<details class="hist"><summary>AI decision history ({len(h)} versions)</summary><table class="list"><tr><th>When</th><th>Source</th>'
                f'<th>Option</th><th>Conf.</th><th></th><th>Check</th><th>Reason for change</th></tr>{rows}</table></details>')
    return out


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
    terms, evl = evidence_terms(it)
    if any(it.get(k) for k in ("base", "source", "target")):
        aid = it["id"]
        snippets = f'''<div class="cols cols4">
  <div class="c-base"><h5>Base (common ancestor)</h5>{code_block(it.get("base"), "del", terms, evl, aid + "-base")}</div>
  <div class="c-src"><h5>Source — incoming</h5>{code_block(it.get("source"), "add", terms, evl, aid + "-source")}</div>
  <div class="c-tgt"><h5>Target — current</h5>{code_block(it.get("target"), "chg", terms, evl, aid + "-target")}</div>
  <div class="c-res"><h5>Result — after the chosen option</h5><div class="resbody"><div class="code empty">Pick an option to preview the result.</div></div></div>
</div>'''
    ai = ""
    if it.get("ai_analysis") or it.get("ai_recommendation"):
        prop = ""
        if it.get("proposed_code"):
            prop = f'<h5>Proposed merged code</h5><pre class="proposal">{esc(it["proposed_code"])}</pre>'
        rec = it.get("recommended_option")
        conf = it.get("ai_confidence")
        hits = ev_hits(it, terms, evl)
        bullets = [b.strip() for b in re.split(r";\s+|\.\s+(?=[A-Z])", it.get("ai_evidence") or "") if len(b.strip()) > 3]
        why = ""
        if rec or conf is not None or bullets:
            pct = int(round((conf or 0) * 100))
            cv = (it.get("check_verdict") or "").lower()
            why = (f'<div class="why"><div class="whyh"><b>Why the AI chose {esc(lab.get(rec, rec) if rec else "—")}</b>'
                   + (f'<span class="meter" title="confidence {esc(conf)}"><i style="width:{pct}%" class="{"hi" if pct >= 90 else "mid" if pct >= 80 else "lo"}"></i></span><b>{pct}%</b>' if conf is not None else "")
                   + (f'<span class="qchip {"ok" if cv.startswith("agree") else "bad"}">2nd check: {esc(it.get("check_verdict"))}{(" · " + esc(it.get("check_by"))) if it.get("check_by") else ""}</span>' if cv else '<span class="qchip warn">no independent check</span>')
                   + "</div>"
                   + ("<ul>" + "".join(f"<li>{esc(b)}</li>" for b in bullets[:8]) + "</ul>" if bullets else "")
                   + ("<div class=\"evl\">Evidence in the code: " + " ".join(f'<a href="#{esc(a)}" class="dep" data-jump="1">{lb} L{n}</a>' for lb, a, n in hits[:16]) + "</div>" if hits else
                      "<div class=\"muted\" style=\"font-size:12px\">The evidence names no line shown in the snippets.</div>")
                   + "</div>")
        ai = f'''{why}<div class="ai"><h4>AI analysis</h4><p>{esc(it.get("ai_analysis")).replace(chr(10), "<br>")}</p>
<h4>AI recommendation{(": " + esc(lab.get(rec, rec))) if rec else ""}{(" · confidence " + esc(it.get("ai_confidence"))) if it.get("ai_confidence") is not None else ""}</h4><p>{esc(it.get("ai_recommendation")).replace(chr(10), "<br>")}</p>{prop}
{("<h5>Evidence</h5><p>" + esc(it.get("ai_evidence")) + "</p>") if it.get("ai_evidence") else ""}
{("<h5>Independent check: " + esc(it.get("check_verdict")) + "</h5><p>" + esc(it.get("check_note") or "") + "</p>") if it.get("check_verdict") else ""}</div>'''
    elif it.get("needs_decision"):
        ai = '<div class="ai pending">AI review pending for this item.</div>'
    dec = ""
    if it.get("escalated"):
        dec += ('<div class="esc"><b>Needs you:</b> ' + esc("; ".join(it.get("escalation_reasons") or [])) + '</div>')
    elif it.get("decided_by") == "ai":
        who = ", ".join(it.get("reviewed_by_developer") or [])
        dec += (f'<div class="aidec">Decided by AI: <b>{esc(lab.get(it.get("decision"), it.get("decision")))}</b>'
                + (f' — <b>confirmed by {esc(who)}</b> (applied from their decisions file)' if who else
                   ' — change the option below to override (before the developer commits).') + '</div>')
    elif it.get("decided_by") == "developer" or (it.get("decision") and it.get("needs_decision")):
        who = ", ".join(it.get("reviewed_by_developer") or []) or "developer"
        dec += (f'<div class="aidec">Decided by <b>{esc(who)}</b>: <b>{esc(lab.get(it.get("decision"), it.get("decision")))}</b>'
                + (f' <span class="muted">(AI had: {esc(lab.get(it.get("recommended_option"), it.get("recommended_option")))})</span>'
                   if it.get("recommended_option") and it.get("recommended_option") != it.get("decision") else '')
                + (f'<div style="margin-top:4px">Their note: {esc(it.get("decision_notes"))}</div>' if (it.get("decision_notes") or "").strip()
                   and not str(it.get("decision_notes")).startswith("AI (confidence") else '') + '</div>')
    if decision_ui:
        radios = "".join(
            f'<label class="opt{" rec" if o == it.get("recommended_option") else ""}"><input type="radio" name="d-{esc(it["id"])}" value="{o}"'
            f'{" checked" if it.get("decision") == o else ""}> {esc(lab[o])}{" ★" if o == it.get("recommended_option") else ""}</label>'
            for o in OPTIONS if not (o == "AI" and not it.get("proposed_code") and not it.get("ai_recommendation")))
        devby = ", ".join(it.get("reviewed_by_developer") or (["developer"] if it.get("decided_by") == "developer" else []))
        dec += f'''<div class="decision" data-id="{esc(it["id"])}"{f' data-devby="{esc(devby)}"' if devby else ''}><div class="opts">{radios}</div>
<textarea placeholder="Notes for this decision (who agreed, what exactly to keep)…" data-notes="{esc(it["id"])}">{esc(it.get("decision_notes"))}</textarea></div>'''
    return f'''<section class="card sev-{esc(it["severity"])}" id="{esc(it["id"])}" data-risk="{" ".join(risks_of(it) + qual_tokens(it))}" data-deps="{esc(" ".join(it.get("depends_on") or []))}" data-area="{esc(area_of(it))}" data-rec="{esc(it.get("recommended_option") or "")}">
<header><a class="iid" href="#{esc(it["id"])}" title="Link to this card (click to copy)">{esc(it["id"])}</a>{badge(cat)}<span class="sev">{esc(it["severity"]).upper()}</span><span class="ttl">{esc(it["title"])}</span></header>
<div class="path">{path_line}</div>{mapping}{quality_chips(it)}
<div class="devs"><div><h5>Incoming (source) — who wrote these exact lines</h5>{people(it.get("source_authors"))}</div><div><h5>Current (target) — who wrote the conflicting lines</h5>{people(it.get("target_authors"))}</div></div>
{"<ul class='signals'>" + signals + "</ul>" if signals else ""}{summary}{snippets}{ai}{extras(it)}{dec}</section>'''


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
.risks{margin:6px 0}.risk{display:inline-block;font-size:11px;font-weight:700;padding:1px 8px;border-radius:10px;margin:0 6px 4px 0;background:#fff3e0;color:#8a4b00;border:1px solid #ffcc80}
.risk.r-drops,.risk.r-doubt,.risk.r-recheck,.risk.r-reverted,.risk.r-secret{background:#fdecea;color:#b71c1c;border-color:#ef9a9a}.risk.r-lookalike{background:#e3f2fd;color:#0d47a1;border-color:#90caf9}
.deps{font-size:13px;margin-top:6px}.dep{font:12px SFMono-Regular,Menlo,monospace;background:#eef2f6;border-radius:6px;padding:1px 6px;margin-right:4px;text-decoration:none}
.cp{background:#e3f2fd;border:1px solid #90caf9;border-radius:8px;padding:8px 12px;margin-top:10px;font-size:13px}.cp ul{margin:4px 0;padding-left:20px}
#repo-risks{background:#fff;border:1px solid #dde3ea;border-radius:10px;padding:10px 16px;margin-top:14px}#repo-risks li{margin:4px 0}
#repo-risks .lv{font-size:11px;font-weight:700;padding:1px 7px;border-radius:9px;margin-right:6px}.lv.block{background:#fdecea;color:#b71c1c}.lv.warn{background:#fff3e0;color:#8a4b00}.lv.info{background:#eef2f6;color:#455a64}
details.hist{margin-top:8px;font-size:12px}details.hist table{font-size:12px}
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
function progress(){const need=[...document.querySelectorAll('.need .decision')];const done=need.filter(el=>el.querySelector('input[type=radio]:checked')).length;
 document.getElementById('progress').textContent=`${done} / ${need.length} required decisions made`;}
function exportJson(){const out={report_id:RID,exported_at:new Date().toISOString(),decided_by:document.getElementById('by').value,decisions:collect()};
 const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(out,null,2)],{type:'application/json'}));
 a.download='decisions-'+RID+'.json';a.click();}
function copyResume(){const t=document.getElementById('resumecmd').textContent;navigator.clipboard&&navigator.clipboard.writeText(t);}
document.addEventListener('change',save);document.addEventListener('input',e=>{if(e.target.tagName==='TEXTAREA'||e.target.id==='by')save();});
window.addEventListener('load',()=>{load();progress();});
"""

# ---- Developer review tracker, merge-readiness gate, multi-reviewer import, persistence (browser + auto-save file).
# Kept separate from JS because JS is %-formatted and this code contains "%".
TRACKER_CSS = r"""
.rs{font-size:11px;font-weight:700;padding:2px 8px;border-radius:10px;margin-left:auto;white-space:nowrap}
.rs.pend{background:#fff3e0;color:#b45309;border:1px solid #ffcc80}.rs.done{background:#e8f5e9;color:#1b5e20;border:1px solid #a5d6a7}
.rs.conf{background:#fdecea;color:#b71c1c;border:1px solid #ef9a9a}
.card.is-done{border-left-color:#2e7d32!important;background:#fbfefb}.card.is-conf{border-left-color:#b71c1c!important;background:#fffafa}
.confirm{display:inline-flex;align-items:center;gap:6px;margin-top:6px;font-size:13px;color:#37474f;cursor:pointer}
.chip{font-size:12px;background:#eef2f6;border-radius:10px;padding:2px 8px;font-weight:700}
.chip.ok{background:#e8f5e9;color:#1b5e20}.chip.bad{background:#fdecea;color:#b71c1c}
.bar select{border:1px solid #cfd8dc;border-radius:6px;padding:6px;max-width:230px}.bar .sec{background:#546e7a}
#tracker{background:#fff;border:1px solid #dde3ea;border-radius:10px;padding:12px 16px;margin-top:16px}
#tracker h3{margin:0 0 6px;font-size:16px}#tracker .grp{margin:8px 0}#tracker .grp b{display:block;font-size:12px;color:#5b6775;margin-bottom:4px}
#tracker a.t{display:inline-block;font:11px SFMono-Regular,Menlo,monospace;padding:2px 6px;margin:2px;border-radius:6px;text-decoration:none;border:1px solid}
#tracker a.t.pend{background:#fff8e1;color:#8a5a00;border-color:#ffe082}#tracker a.t.done{background:#e8f5e9;color:#1b5e20;border-color:#a5d6a7}
button.cpbtn{background:#4a154b;color:#fff;border:0;border-radius:6px;padding:4px 10px;font-weight:600;font-size:12px;cursor:pointer;margin-left:6px}
button.cpbtn.alt{background:#546e7a}#cptoast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:#263238;color:#fff;padding:8px 14px;border-radius:8px;font-size:13px;z-index:20;display:none}
table.pairs{border-collapse:collapse;font-size:13px;margin-top:6px;width:100%}table.pairs th,table.pairs td{border-bottom:1px solid #e3e8ee;padding:5px 8px;text-align:left;vertical-align:top}
table.pairs th{background:#eef2f6}table.pairs td.who b{display:block}table.pairs td.who span{font-size:11px;color:#78909c}table.pairs .pri{font-weight:700;color:#b71c1c}
table.pairs tr.done td{opacity:.55}table.pairs a.t{margin:1px}
#tracker a.t.conf{background:#fdecea;color:#b71c1c;border-color:#ef9a9a}#tracker a.t.dim{opacity:.25}
.hcount{font-size:13px;font-weight:600;color:#b45309;margin-left:8px}.hcount.ok{color:#2e7d32}
.rmeter{height:8px;background:#eef2f6;border-radius:4px;overflow:hidden;margin:6px 0}.rmeter i{display:block;height:100%;background:#2e7d32}
.ready{border-radius:8px;padding:10px 12px;margin:8px 0 10px}.ready.bad{background:#fdecea;border:1px solid #f5c2c0}.ready.ok{background:#e8f5e9;border:1px solid #a5d6a7}
.ready ul{margin:4px 0 0;padding-left:20px}.ready li{margin:2px 0}
.revs{margin-top:8px;font-size:13px;background:#f3f6f9;border:1px solid #dde3ea;border-radius:6px;padding:6px 10px}
.revs.conf{background:#fdecea;border-color:#f5c2c0}.revs div{margin:2px 0}
table.devt{border-collapse:collapse;font-size:13px;margin-top:6px}table.devt th,table.devt td{border-bottom:1px solid #e3e8ee;padding:3px 10px;text-align:left}
table.devt th{background:#eef2f6}table.devt a{cursor:pointer}
.imps{font-size:13px;margin-top:6px}.imps code{background:#eef2f6;padding:0 4px;border-radius:3px}
dialog#pdlg{width:min(900px,95vw);border:1px solid #cfd8dc;border-radius:10px;padding:14px}dialog#pdlg textarea{min-height:50vh;font:12px/1.45 SFMono-Regular,Menlo,monospace}
dialog#pdlg .row{display:flex;gap:8px;justify-content:flex-end;margin-top:8px}dialog#pdlg button{background:#1565c0;color:#fff;border:0;border-radius:6px;padding:7px 12px;font-weight:600;cursor:pointer}
@media print{#tracker .grp,.confirm{display:none}}
"""

TRACKER_BAR = '<span id="rsave" style="display:inline-flex;gap:6px;align-items:center"></span><span id="rready" class="chip"></span><span id="rstat" class="chip"></span><select id="rfilter" title="Show cards"><option value="all">Status: all</option><option value="pend">Status: pending</option><option value="done">Status: reviewed</option><option value="conf">Status: reviewers disagree</option></select><select id="rdev" title="Filter by developer"><option value="">Developer: everyone</option></select><button class="sec" onclick="nextPending()">Next pending ▶</button><button class="sec" onclick="showPendingList()">Pending list</button><button class="sec" onclick="document.getElementById(\'importf\').click()">Import decisions (.json)</button><input type="file" id="importf" accept=".json,application/json" multiple style="display:none">'

TRACKER_DIALOG = ('<dialog id="pdlg"><b id="pdlgt">Pending list</b><textarea id="pdlgx" readonly></textarea>'
                  '<div class="row"><button onclick="copyPending()">Copy</button><button style="background:#546e7a" onclick="this.closest(\'dialog\').close()">Close</button></div></dialog>')

TRACKER_JS = r"""
/* ===== Developer review tracker =====
   Reviewed = selection changed from the default, own comment added, or "Mark reviewed" ticked —
   in this browser or in an imported decisions file. Pre-filled AI choices/notes alone do not count. */
const IKEY=KEY+'-imports';
const SECS=[['recheck','AI re-check pending'],['decide','Needs you'],['aidecided','Decided by AI'],['devdecided','Decided by developer'],['review','Review']];
const SECNAME=Object.fromEntries(SECS);
const esc=t=>String(t).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function secOf(card){for(let n=card.parentElement;n&&n!==document.body;n=n.parentElement){let x=n.previousElementSibling;
 while(x&&!(x.tagName==='H2'&&x.id))x=x.previousElementSibling;if(x)return x.id;}return 'review';}
const EMAIL={};let LASTPAIRS=[];
function toast(m){let t=document.getElementById('cptoast');if(!t){t=document.createElement('div');t.id='cptoast';document.body.appendChild(t);}t.textContent=m;t.style.display='block';clearTimeout(t._h);t._h=setTimeout(()=>t.style.display='none',3500);}
function pairsText(){const R=readiness();const by=document.getElementById('by').value;
 let t=`*Merge review — who needs to talk to whom*\n${RID}\nStatus: ${R.summary} · ${LASTPAIRS.length} pairs with open cards`+(by?` · shared by ${by}`:'')+`\n`;
 LASTPAIRS.forEach(p=>{t+=`\n• *${p.s}* ↔ *${p.s===p.t?'(self-review)':p.t}* — `+(p.undec?`${p.undec} decision${p.undec>1?'s':''} pending, `:'all decided, ')+(p.need?`:red_circle: ${p.need} blocking, `:'')+`${p.pend} not reviewed`+(p.conf?`, ${p.conf} reviewers disagree`:'')+`\n    ${p.ids.join(', ')}`;});
 return t+`\n\nOpen report.html → Tracker → “Who needs to talk to whom”. Blocking = Needs you / AI re-check.`;}
function copyText(txt,label){const done=()=>toast(label+' copied — paste into Slack');
 const fallback=()=>{const d=document.getElementById('pdlg');document.getElementById('pdlgt').textContent=label+' (select all and copy)';document.getElementById('pdlgx').value=txt;if(d.showModal)d.showModal();else d.setAttribute('open','');};
 if(navigator.clipboard&&navigator.clipboard.writeText)navigator.clipboard.writeText(txt).then(done,fallback);else fallback();}
function pairsCanvas(){const S=2,W=1500,pad=24,rowGap=10,font='-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif';
 const cols=[{x:pad,w:220,h:'Incoming (source)'},{x:pad+230,w:220,h:'Current (target)'},{x:pad+460,w:660,h:'Open cards to discuss'},{x:pad+1130,w:120,h:'Decisions pending'},{x:pad+1260,w:80,h:'Blocking'},{x:pad+1350,w:120,h:'Not reviewed/total'}];
 const c=document.createElement('canvas'),g=c.getContext('2d');g.font='12px SFMono-Regular,Menlo,monospace';  /* measure in the font the IDs are drawn in */
 const wrap=(ids,w)=>{w-=12;const lines=[];let cur='';ids.forEach(id=>{const nx=cur?cur+'  '+id:id;if(g.measureText(nx).width>w&&cur){lines.push(cur);cur=id;}else cur=nx;});if(cur)lines.push(cur);return lines.length?lines:['—'];};
 const rows=LASTPAIRS.map(p=>{const L=wrap(p.ids,cols[2].w);return {p,L,h:Math.max(2,L.length)*18+rowGap};});
 const head=92,H=head+34+rows.reduce((a,r)=>a+r.h,0)+pad;c.width=W*S;c.height=H*S;g.scale(S,S);
 g.fillStyle='#ffffff';g.fillRect(0,0,W,H);g.fillStyle='#1c2430';g.font='bold 20px '+font;g.fillText('Merge review — who needs to talk to whom',pad,34);
 g.font='13px '+font;g.fillStyle='#5b6775';const R=readiness();g.fillText(RID+'  ·  '+R.summary+'  ·  '+LASTPAIRS.length+' pairs with open cards  ·  '+new Date().toLocaleString(),pad,58);
 g.fillStyle='#eef2f6';g.fillRect(pad-8,head-22,W-2*pad+16,30);g.fillStyle='#1c2430';g.font='bold 13px '+font;cols.forEach(k=>g.fillText(k.h,k.x,head-2));
 let y=head+28;rows.forEach((r,i)=>{if(i%2)(g.fillStyle='#fafbfc',g.fillRect(pad-8,y-16,W-2*pad+16,r.h));
  g.font='bold 13px '+font;g.fillStyle='#4527a0';g.fillText(r.p.s,cols[0].x,y);g.fillText(r.p.s===r.p.t?'(self-review)':r.p.t,cols[1].x,y);
  g.font='11px '+font;g.fillStyle='#78909c';if(EMAIL[r.p.s])g.fillText(EMAIL[r.p.s].slice(0,34),cols[0].x,y+16);if(EMAIL[r.p.t]&&r.p.s!==r.p.t)g.fillText(EMAIL[r.p.t].slice(0,34),cols[1].x,y+16);
  g.font='12px SFMono-Regular,Menlo,monospace';g.fillStyle='#8a5a00';r.L.forEach((l,j)=>g.fillText(l,cols[2].x,y+j*18));
  g.font='bold 14px '+font;g.fillStyle=r.p.undec?'#c62828':'#2e7d32';g.fillText(r.p.undec?String(r.p.undec):'0 ✓',cols[3].x,y);
  g.fillStyle=r.p.need?'#c62828':'#5b6775';g.fillText(String(r.p.need)+(r.p.conf?'  ⚠'+r.p.conf:''),cols[4].x,y);
  g.font='13px '+font;g.fillStyle='#1c2430';g.fillText(r.p.pend+' / '+r.p.total,cols[5].x,y);
  g.strokeStyle='#e3e8ee';g.beginPath();g.moveTo(pad-8,y+r.h-16);g.lineTo(W-pad+8,y+r.h-16);g.stroke();y+=r.h;});
 return c;}
function copyImage(){const c=pairsCanvas();c.toBlob(b=>{const dl=()=>{const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='merge-review-pairs.png';a.click();toast('Image downloaded — drag merge-review-pairs.png into Slack');};
 try{if(navigator.clipboard&&window.ClipboardItem){navigator.clipboard.write([new ClipboardItem({'image/png':b})]).then(()=>toast('Image copied — paste into Slack (⌘V)'),dl);}else dl();}catch(e){dl();}},'image/png');}
document.addEventListener('click',e=>{const b=e.target.closest('button.cpbtn');if(!b)return;e.preventDefault();
 if(b.dataset.act==='pairs-text')copyText(pairsText(),'Pairs list');else if(b.dataset.act==='pairs-img')copyImage();});
function devsOf(card,i){const col0=card.querySelectorAll('.devs > div')[i];if(col0)col0.querySelectorAll('.dev').forEach(dv=>{const b=dv.querySelector('b');const m=dv.textContent.match(/<([^>\s]+@[^>\s]+)>/);if(b&&m)EMAIL[b.textContent.trim()]=m[1];});
const col=card.querySelectorAll('.devs > div')[i];return col?[...new Set([...col.querySelectorAll('.dev > b:first-child')].map(b=>b.textContent.trim()))]:[];}
const CARDS=[...document.querySelectorAll('.decision')].map(el=>{const card=el.closest('.card');
 const def=[...el.querySelectorAll('input[type=radio]')].find(r=>r.defaultChecked);const ta=el.querySelector('textarea');
 const revs=document.createElement('div');revs.className='revs';revs.hidden=true;el.appendChild(revs);
 const lab=document.createElement('label');lab.className='confirm';lab.innerHTML='<input type="checkbox" class="rv"> Mark reviewed (I checked this point)';el.appendChild(lab);
 const b=document.createElement('span');b.className='rs pend';card.querySelector('header').appendChild(b);
 const src=devsOf(card,0),tgt=devsOf(card,1);
 return {id:el.dataset.id,el,card,badge:b,revs,sec:secOf(card),defChoice:def?def.value:null,defNotes:(ta.defaultValue||'').trim(),
  src,tgt,devs:[...new Set([...src,...tgt])],path:(card.querySelector('.path code')||{}).textContent||'',title:(card.querySelector('.ttl')||{}).textContent||''};});
const BYID=Object.fromEntries(CARDS.map(c=>[c.id,c]));
let IMPORTS={};try{IMPORTS=JSON.parse(localStorage.getItem(IKEY)||'{}')||{};}catch(e){}
function saveImports(){try{localStorage.setItem(IKEY,JSON.stringify(IMPORTS));}catch(e){}}

function localOf(c){const r=c.el.querySelector('input[type=radio]:checked');const n=c.el.querySelector('textarea').value.trim();
 return {choice:r?r.value:null,notes:n,sel:!!r&&r.value!==c.defChoice,com:!!n&&n!==c.defNotes,conf:c.el.querySelector('.rv').checked};}
function impDone(v,c){const n=(v.notes||'').trim();return !!(v.reviewed||/^REVIEWED/.test(v.status||'')||(v.choice&&v.choice!==c.defChoice)||(n&&n!==c.defNotes));}
function impsOf(c){return Object.entries(IMPORTS).map(([who,f])=>{const v=(f.decisions||{})[c.id];return v?{who,choice:v.choice||null,notes:(v.notes||'').trim(),done:impDone(v,c)}:null;}).filter(Boolean);}
function stateOf(c){const L=localOf(c),I=impsOf(c).filter(x=>x.done);
 const why=[L.sel&&'selected',L.com&&'commented',L.conf&&'confirmed'].filter(Boolean);if(I.length)why.push('by '+I.map(x=>x.who).join(', '));
 if(c.el.dataset.devby&&!I.some(x=>c.el.dataset.devby.includes(x.who)))why.push('by '+c.el.dataset.devby);
 const picks=[...new Set(I.map(x=>x.choice).filter(Boolean))];
 const conflict=picks.length>1&&!(L.conf&&L.choice); /* reviewers disagree until someone here ticks "Mark reviewed" with the final choice */
 const agreed=picks.length===1?picks[0]:null;
 const custNoNote=(L.sel?L.choice:(agreed||L.choice))==='CUSTOM'&&!L.notes.trim()&&!I.some(x=>x.notes);  /* any written note counts, incl. a developer note already recorded in the report */
 return {done:why.length>0,why,conflict,picks,I,L,agreed,custNoNote};}

const _collect=collect;collect=function(){const d=_collect();CARDS.forEach(c=>{if(c.el.querySelector('.rv').checked){d[c.id]=d[c.id]||{choice:null,notes:''};d[c.id].reviewed=true;}});return d;};
function applyLocal(dd){for(const[id,v]of Object.entries(dd||{})){if(v.choice){const r=document.querySelector(`input[name="d-${id}"][value="${v.choice}"]`);if(r)r.checked=true;}
 const t=document.querySelector(`textarea[data-notes="${id}"]`);if(t&&typeof v.notes==='string'&&v.notes)t.value=v.notes;
 if(BYID[id]&&v.reviewed)BYID[id].el.querySelector('.rv').checked=true;}}
const _load=load;load=function(){_load();try{const s=JSON.parse(localStorage.getItem(KEY)||'null');if(s)applyLocal(s.d);}catch(e){}};

/* Export: this browser's choices + agreed choices from imported files, with who reviewed what. Same shape the merge tool reads. */
function buildOut(){const by=document.getElementById('by').value;const dec={};
 CARDS.forEach(c=>{const st=stateOf(c),L=st.L;const choice=(L.sel||L.conf)?L.choice:(st.agreed||L.choice);
  const notes=[L.notes,...st.I.filter(x=>x.notes&&x.notes!==c.defNotes&&x.notes!==L.notes).map(x=>`[${x.who}] ${x.notes}`)].filter(Boolean).join('\n');
  if(!choice&&!notes&&!st.done)return;
  dec[c.id]={choice,notes,status:st.conflict?'CONFLICT':st.done?'REVIEWED':'PENDING',reviewed_by:[...(L.sel||L.com||L.conf?[by||'(this browser)']:[]),...st.I.map(x=>x.who)],
   ...(st.I.length?{reviewer_choices:Object.fromEntries(st.I.map(x=>[x.who,x.choice]))}:{}),...(L.conf?{reviewed:true}:{})};});
 const out={report_id:RID,exported_at:new Date().toISOString(),decided_by:by,merged_from:Object.keys(IMPORTS),readiness:readiness().summary,acknowledged_risks:[...document.querySelectorAll('.rack')].filter(x=>x.checked).map(x=>x.dataset.ack),decisions:dec};
 return out;}
exportJson=function(){const out=buildOut();const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(out,null,2)],{type:'application/json'}));
 a.download='decisions-'+RID+'.json';a.click();};

function readiness(){const block=[],warn=[];
 CARDS.forEach(c=>{const st=stateOf(c);const lnk=`<a href="#${c.id}">${c.id}</a>`;
  if(c.sec==='decide'&&!st.L.choice&&!st.agreed)block.push(`${lnk} (Needs you) has no option selected`);
  if(st.conflict)block.push(`${lnk} reviewers disagree: ${st.I.filter(x=>x.choice).map(x=>esc(x.who)+' → '+x.choice).join(', ')} — pick the final option and tick “Mark reviewed”`);
  if(st.custNoNote)block.push(`${lnk} is set to <b>Custom</b> but nobody wrote what to keep`);
  const chg=(c.card.dataset.deps||'').split(' ').filter(x=>BYID[x]&&stateOf(BYID[x]).L.sel);
  if(chg.length&&!st.L.sel&&!st.L.conf)block.push(`${lnk} depends on ${chg.join(', ')}, which was changed here — review it again and tick “Mark reviewed”`);
  if(c.sec!=='decide'&&c.sec!=='recheck'&&!st.done)warn.push(c);});
 document.querySelectorAll('.rack').forEach(x=>{if(!x.checked)block.push(`Repository risk <a href="#repo-risks">${esc(x.dataset.ack)}</a> not acknowledged`);});
 CARDS.forEach(c=>{const st=stateOf(c);if(c.sec==='recheck'&&!st.done)block.push(`<a href="#${c.id}">${c.id}</a> — AI re-check pending: the agent must finish its review (or a developer decides / ticks “Mark reviewed”)`);});
 const ok=!block.length;return {ok,block,warn,summary:ok?(warn.length?`READY (${warn.length} non-blocking cards not reviewed)`:'READY'):`BLOCKED (${block.length})`};}

const AKEY2=KEY+'-acks';try{const s=JSON.parse(localStorage.getItem(AKEY2)||'{}');document.querySelectorAll('.rack').forEach(x=>{if(s[x.dataset.ack])x.checked=true;});}catch(e){}
document.addEventListener('change',e=>{if(e.target.classList&&e.target.classList.contains('rack')){const s={};document.querySelectorAll('.rack').forEach(x=>{if(x.checked)s[x.dataset.ack]=true;});try{localStorage.setItem(AKEY2,JSON.stringify(s));}catch(_){}refresh();}});
function matchDev(c){const d=document.getElementById('rdev').value,k=(document.getElementById('rrisk')||{}).value;
 return (!d||c.devs.includes(d))&&(!k||(c.card.dataset.risk||'').split(' ').includes(k));}
function refresh(){const f=document.getElementById('rfilter').value;let tot=0,dn=0;const per={},dev={};
 CARDS.forEach(c=>{const st=stateOf(c);c._st=st;tot++;if(st.done)dn++;(per[c.sec]=per[c.sec]||{t:0,d:0,items:[]});per[c.sec].t++;if(st.done)per[c.sec].d++;per[c.sec].items.push(c);
  c.devs.forEach(n=>{const x=dev[n]=dev[n]||{src:0,tgt:0,pend:0,t:0};x.t++;if(c.src.includes(n))x.src++;if(c.tgt.includes(n))x.tgt++;if(!st.done)x.pend++;});
  const k=st.conflict?'conf':st.done?'done':'pend';
  c.badge.className='rs '+k;c.badge.textContent=st.conflict?'⚠ Reviewers disagree':st.done?'✓ Reviewed — '+st.why.join(' + '):'⏳ Pending review';
  c.card.classList.toggle('is-done',st.done&&!st.conflict);c.card.classList.toggle('is-conf',st.conflict);
  const show=(f==='all'||(f==='conf'?st.conflict:f==='done'?st.done:!st.done))&&matchDev(c);c.card.style.display=show?'':'none';
  if(st.I.length||impsOf(c).length){const all=impsOf(c);c.revs.hidden=false;c.revs.className='revs'+(st.conflict?' conf':'');
   c.revs.innerHTML='<b>Imported reviews</b>'+all.map(x=>`<div><b>${esc(x.who)}</b>: ${x.choice?'<code>'+x.choice+'</code>':'<i>no option</i>'}${x.notes&&x.notes!==c.defNotes?' — '+esc(x.notes):''}${x.done?'':' <span class="muted">(left as default)</span>'}</div>`).join('');}
  else c.revs.hidden=true;});
 /* developer dropdown */
 const sel=document.getElementById('rdev'),cur=sel.value;const names=Object.keys(dev).sort((a,b)=>dev[b].pend-dev[a].pend||a.localeCompare(b));
 sel.innerHTML='<option value="">Developer: everyone</option>'+names.map(n=>`<option value="${esc(n)}">${esc(n)} (${dev[n].pend} pending / ${dev[n].t})</option>`).join('');sel.value=cur;
 const R=readiness();
 document.getElementById('rstat').textContent=`Reviewed ${dn} / ${tot} · Pending ${tot-dn}`;
 const rr=document.getElementById('rready');rr.className='chip '+(R.ok?'ok':'bad');rr.textContent=R.ok?'✓ Ready to merge':`⛔ Blocked (${R.block.length})`;rr.title=R.summary;
 let h=`<h3>Developer review tracker</h3>`;
 h+=R.ok?`<div class="ready ok"><b>✓ Ready to merge</b> — all “Needs you” cards have an option, no Custom choice is missing notes, and no reviewers disagree.${R.warn.length?` ${R.warn.length} non-blocking cards (AI-decided / Review) are still unreviewed.`:''}</div>`
  :`<div class="ready bad"><b>⛔ Not ready to merge — ${R.block.length} blocker${R.block.length>1?'s':''}</b><ul>${R.block.map(x=>'<li>'+x+'</li>').join('')}</ul>${R.warn.length?`<div class="muted" style="margin-top:4px">Also ${R.warn.length} non-blocking cards still unreviewed.</div>`:''}</div>`;
 h+=`<div class="muted">A card is <b>reviewed</b> when someone changed the selection from its default, wrote their own comment, or ticked “Mark reviewed” — here or in an imported file. Pre-filled AI choices/notes alone do not count.</div>`;
 h+=`<div class="rmeter"><i style="width:${tot?dn*100/tot:0}%"></i></div><b>${dn} reviewed · ${tot-dn} pending</b> of ${tot} decision cards`;
 const dv=sel.value;
 SECS.forEach(([sid,name])=>{const p=per[sid];if(!p)return;const H=document.getElementById(sid);
  if(H){let sp=H.querySelector('.hcount');if(!sp){sp=document.createElement('span');sp.className='hcount';H.appendChild(sp);}
   sp.className='hcount'+(p.d===p.t?' ok':'');sp.textContent=`· ${p.d} reviewed / ${p.t-p.d} pending`;}
  h+=`<div class="grp"><b>${name}: ${p.d} reviewed / ${p.t-p.d} pending</b>`+p.items.map(c=>{const st=c._st;const k=st.conflict?'conf':st.done?'done':'pend';
   return `<a class="t ${k}${!matchDev(c)?' dim':''}" href="#${c.id}" title="${esc((st.conflict?'Reviewers disagree':st.done?'Reviewed: '+st.why.join(', '):'Pending')+' · '+c.devs.join(', '))}">${c.id}</a>`;}).join('')+'</div>';});
 /* ---- who needs to talk to whom: incoming (source) author ↔ current (target) author of the SAME lines ---- */
 const pairs={};
 CARDS.forEach(c=>{const st=c._st;const S=c.src.length?c.src:['(author not found)'],T=c.tgt.length?c.tgt:['(author not found)'];
  const undecided=!(st.L.choice||st.agreed)||st.conflict;
  S.forEach(s=>T.forEach(t=>{const k=s+'\u0001'+t;const p=pairs[k]=pairs[k]||{s,t,cards:[],pend:0,need:0,conf:0,undec:0};
   p.cards.push(c);if(undecided)p.undec++;if(!st.done||st.conflict){p.pend++;if(c.sec==='decide'||c.sec==='recheck')p.need++;}if(st.conflict)p.conf++;}));});
 const PL=Object.values(pairs).sort((a,b)=>b.need-a.need||b.undec-a.undec||b.pend-a.pend||b.cards.length-a.cards.length);
 const who=n=>`<b>${esc(n)}</b>${EMAIL[n]?`<span>${esc(EMAIL[n])}</span>`:''}`;
 const openP=PL.filter(p=>p.pend).length;
 LASTPAIRS=PL.filter(p=>p.pend).map(p=>({s:p.s,t:p.t,need:p.need,conf:p.conf,pend:p.pend,total:p.cards.length,undec:p.undec,
   ids:p.cards.filter(c=>!c._st.done||c._st.conflict).sort((a,b)=>(b.sec==='decide')-(a.sec==='decide')).map(c=>c.id)}));
 h+=`<details open><summary>Who needs to talk to whom (${openP} pair${openP===1?'':'s'} with open cards)</summary>`+
  `<div style="margin:6px 0">Share in Slack: <button class="cpbtn" data-act="pairs-text">Copy as text</button><button class="cpbtn alt" data-act="pairs-img">Copy as image</button></div>`+
  `<div class="muted" style="margin:4px 0"><b>Decisions pending</b> = cards where no option is chosen yet (or reviewers disagree); <b>Not reviewed</b> also counts cards that have an AI decision nobody has checked. Each row pairs the developer who wrote the incoming (source) lines with the developer who wrote the conflicting current (target) lines on the same card. Meet in this order; <span class="pri">red</span> = cards that block the merge (Needs you / AI re-check).</div>`+
  `<table class="pairs"><tr><th>Incoming (source) developer</th><th>Current (target) developer</th><th>Open cards to discuss</th><th title="cards with no option chosen yet (or reviewers disagree)">Decisions pending</th><th title="cards that block the merge: Needs you / AI re-check">Blocking</th><th title="cards not reviewed yet / all cards of this pair">Not reviewed / total</th></tr>`+
  PL.map(p=>{const open=p.cards.filter(c=>!c._st.done||c._st.conflict).sort((a,b)=>(b.sec==='decide')-(a.sec==='decide'));
   const same=p.s===p.t;
   return `<tr class="${p.pend?'':'done'}"><td class="who">${who(p.s)}</td><td class="who">${same?'<i>same developer — self-review</i>':who(p.t)}</td>`+
    `<td>${open.map(c=>`<a class="t ${c._st.conflict?'conf':'pend'}" href="#${c.id}" title="${esc(SECNAME[c.sec]+' · '+c.path)}">${c.id}</a>`).join('')||'<span class="muted">all reviewed ✓</span>'}</td>`+
    `<td>${p.undec?`<span class="pri">${p.undec}</span>`:'<span style="color:#2e7d32">0 ✓</span>'}</td>`+
    `<td>${p.need?`<span class="pri">${p.need}</span>`:'0'}${p.conf?` · ⚠ ${p.conf} disagree`:''}</td><td>${p.pend} / ${p.cards.length}</td></tr>`;}).join('')+`</table></details>`;
 h+=`<details><summary>By developer (${names.length})</summary><table class="devt"><tr><th>Developer</th><th>Cards</th><th>Wrote source lines</th><th>Wrote target lines</th><th>Pending</th></tr>`+
  names.map(n=>`<tr><td><a data-dev="${esc(n)}">${esc(n)}</a></td><td>${dev[n].t}</td><td>${dev[n].src}</td><td>${dev[n].tgt}</td><td>${dev[n].pend?'<b>'+dev[n].pend+'</b>':'✓ 0'}</td></tr>`).join('')+`</table></details>`;
 const imp=Object.entries(IMPORTS);const RM=(typeof REPORT_META!=='undefined')?REPORT_META:{applied:[],files:[],auto:0};
 if(RM.applied.length)h+=`<div class="imps"><b>Applied in this report</b> (visible to everyone)${RM.applied_at?` · ${esc(String(RM.applied_at).replace('T',' '))}`:''}: `+
   RM.applied.map(x=>`<code>${esc(x.name)}</code> <span class="muted">(${x.decisions} decisions: ${x.changed} changed, ${x.confirmed} confirmed the AI)</span>`).join(', ')+
   (RM.files.length?`<div class="muted">from ${RM.files.map(f=>'<code>'+esc(f)+'</code>').join(', ')}</div>`:'')+`</div>`;
 h+=`<div class="imps">${imp.length?`Imported files: ${imp.map(([w,f])=>`<code>${esc(w)}</code> <span class="muted">(${Object.keys(f.decisions||{}).length} cards, ${esc((f.exported_at||'').slice(0,16).replace('T',' '))})</span>`).join(', ')} · <a href="#" id="clrimp">clear imported files</a>`
  :`<span class="muted">${RM.applied.length?'No extra files imported in this browser.':'No developer files imported.'} Use “Import decisions (.json)” — you can pick several files at once; each is kept as a separate reviewer (only in this browser until applied to the report).</span>`}</div>`;
 h+=`<div class="muted" style="margin-top:6px">The ${RM.auto||'other'} auto-applied changes have no decision controls, so they are not counted here.</div>`;
 document.getElementById('tracker').innerHTML=h;
 if(f!=='all'||dv||document.getElementById('rrisk').value)document.querySelectorAll('details:not(.hist)').forEach(d=>{if(d.querySelector('.decision'))d.open=true;});}

function nextPending(){const y=window.scrollY+80;const pend=CARDS.filter(c=>{const st=stateOf(c);return (!st.done||st.conflict)&&matchDev(c);});
 if(!pend.length){alert('Nothing pending'+(document.getElementById('rdev').value?' for this developer.':'.'));return;}
 pend.forEach(c=>{const d=c.card.closest('details');if(d)d.open=true;});
 const nx=pend.find(c=>c.card.getBoundingClientRect().top+window.scrollY>y+5)||pend[0];nx.card.style.display='';nx.card.scrollIntoView({behavior:'smooth',block:'start'});}

function pendingText(){const dv=document.getElementById('rdev').value;const groups={};
 CARDS.forEach(c=>{const st=stateOf(c);if(st.done&&!st.conflict)return;(dv?[dv].filter(n=>c.devs.includes(n)):(c.devs.length?c.devs:['(no author)'])).forEach(n=>(groups[n]=groups[n]||[]).push([c,st]));});
 const R=readiness();let t=`Merge review — ${RID}\nStatus: ${R.summary}\nOpen the report, search the card ID, pick an option or add a note (or tick "Mark reviewed"), then send back "Export decisions (.json)".\n`;
 Object.keys(groups).sort((a,b)=>groups[b].length-groups[a].length).forEach(n=>{t+=`\n${n} — ${groups[n].length} pending\n`;
  groups[n].forEach(([c,st])=>{const role=[c.src.includes(n)&&'source author',c.tgt.includes(n)&&'target author'].filter(Boolean).join(' + ');
   t+=`  • ${c.id} [${SECNAME[c.sec]}]${st.conflict?' ⚠ reviewers disagree':''} ${c.path}${role?' ('+role+')':''}\n`;});});
 if(!Object.keys(groups).length)t+='\nNothing pending.\n';
 const pr={};CARDS.forEach(c=>{const st=stateOf(c);if(st.done&&!st.conflict)return;(c.src.length?c.src:['(unknown)']).forEach(s=>(c.tgt.length?c.tgt:['(unknown)']).forEach(x=>{if(dv&&s!==dv&&x!==dv)return;(pr[s+' ↔ '+x]=pr[s+' ↔ '+x]||[]).push(c.id);}));});
 const pk=Object.keys(pr).sort((a,b)=>pr[b].length-pr[a].length);
 if(pk.length){t+='\nMeet to resolve together (incoming ↔ current author):\n';pk.forEach(k=>{t+=`  • ${k}: ${pr[k].join(', ')}\n`;});}
 return t;}
function showPendingList(){const d=document.getElementById('pdlg');const dv=document.getElementById('rdev').value;
 document.getElementById('pdlgt').textContent='Pending list'+(dv?' — '+dv:' — grouped by developer');document.getElementById('pdlgx').value=pendingText();
 if(d.showModal)d.showModal();else d.setAttribute('open','');}
function copyPending(){const x=document.getElementById('pdlgx');x.select();let ok=false;try{ok=document.execCommand('copy');}catch(e){}
 if(navigator.clipboard)navigator.clipboard.writeText(x.value).catch(()=>{});}

document.addEventListener('click',e=>{const a=e.target.closest('#tracker a.t, .ready a');if(a){const c=document.getElementById(a.getAttribute('href').slice(1));const d=c&&c.closest('details');if(d)d.open=true;if(c)c.style.display='';}
 const dd=e.target.closest('#tracker a[data-dev]');if(dd){document.getElementById('rdev').value=dd.dataset.dev;refresh();}
 if(e.target.id==='clrimp'){e.preventDefault();if(confirm('Remove all imported developer files from this report? (Your own choices stay.)')){IMPORTS={};saveImports();refresh();}}});
document.getElementById('importf').addEventListener('change',async e=>{const files=[...e.target.files];e.target.value='';const done=[],bad=[];
 for(const f of files){try{const j=JSON.parse(await f.text());if(j.report_id&&j.report_id!==RID&&!confirm(f.name+' is for '+j.report_id+'. Import anyway?'))continue;
  if(j.autosave&&j.local&&(!j.report_id||j.report_id===RID)&&confirm(f.name+' is a saved-progress file'+(j.decided_by?' from '+j.decided_by:'')+' (saved '+String(j.local.saved_at||'').slice(0,16).replace('T',' ')+').\n\nOK = restore it as MY progress in this browser\nCancel = add it as another reviewer')){restoreLocal(j.local);done.push('your saved progress');continue;}
  const dec=j.decisions||j.d;if(!dec||typeof dec!=='object')throw new Error('no "decisions" in file');
  let who=(j.decided_by||'').trim()||f.name.replace(/\.json$/i,'');const base=who;let i=2;while(IMPORTS[who]&&IMPORTS[who].file!==f.name)who=base+' ('+(i++)+')';
  IMPORTS[who]={file:f.name,exported_at:j.exported_at||'',decisions:dec};done.push(who);}catch(err){bad.push(f.name+': '+err.message);}}
 saveImports();refresh();alert((done.length?'Imported: '+done.join(', '):'Nothing imported')+(bad.length?'\nFailed: '+bad.join('\n'):''));});
const _progress=progress;progress=function(){_progress();refresh();};
document.getElementById('rfilter').addEventListener('change',refresh);document.getElementById('rdev').addEventListener('change',refresh);
if(document.getElementById('rrisk'))document.getElementById('rrisk').addEventListener('change',refresh);

/* ===== Persistence =====
   1) Browser storage (every browser): every change is saved instantly and restored when the report is reopened.
   2) Auto-save file (Chrome / Edge): every change is also written to a JSON file you choose, e.g. next to this report.
      On reopen the file is read back, so progress survives clearing browser data. The same file works as the decisions file for the merge tool. */
const AKEY=KEY+'-at';const FS=!!window.showSaveFilePicker;let FH=null,FSTATE='none',wTimer=null,lastFileAt='',lastErr='';
const nowIso=()=>new Date().toISOString();const hm=t=>t?new Date(t).toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}):'';
function localAt(){try{return localStorage.getItem(AKEY)||'';}catch(e){return '';}}
function idb(){return new Promise((res,rej)=>{const r=indexedDB.open('merge-report-files',1);r.onupgradeneeded=()=>r.result.createObjectStore('h');r.onsuccess=()=>res(r.result);r.onerror=()=>rej(r.error);});}
async function idbGet(){try{const db=await idb();return await new Promise(r=>{const q=db.transaction('h').objectStore('h').get(RID);q.onsuccess=()=>r(q.result||null);q.onerror=()=>r(null);});}catch(e){return null;}}
async function idbSet(v){try{const db=await idb();await new Promise(r=>{const tx=db.transaction('h','readwrite');v?tx.objectStore('h').put(v,RID):tx.objectStore('h').delete(RID);tx.oncomplete=r;tx.onerror=r;});}catch(e){}}
function snapshot(){return {by:document.getElementById('by').value,d:collect(),imports:IMPORTS,saved_at:localAt()||nowIso()};}
function resetInputs(){CARDS.forEach(c=>{c.el.querySelectorAll('input[type=radio]').forEach(r=>r.checked=r.defaultChecked);const t=c.el.querySelector('textarea');t.value=t.defaultValue;c.el.querySelector('.rv').checked=false;});}
function restoreLocal(L){resetInputs();applyLocal(L.d||{});document.getElementById('by').value=L.by||document.getElementById('by').value;IMPORTS=L.imports||{};
 try{localStorage.setItem(IKEY,JSON.stringify(IMPORTS));localStorage.setItem(KEY,JSON.stringify({by:document.getElementById('by').value,d:collect()}));localStorage.setItem(AKEY,L.saved_at||nowIso());}catch(e){}
 progress();queueWrite();}
function touched(){try{localStorage.setItem(AKEY,nowIso());}catch(e){}queueWrite();showSaved();}
function queueWrite(){if(!FH||FSTATE!=='ok')return;clearTimeout(wTimer);wTimer=setTimeout(writeFile,600);}
async function writeFile(){if(!FH)return;try{const out=buildOut();out.autosave=true;out.local=snapshot();const w=await FH.createWritable();await w.write(JSON.stringify(out,null,2));await w.close();lastFileAt=out.local.saved_at;FSTATE='ok';lastErr='';}
 catch(e){FSTATE=(e&&e.name==='NotAllowedError')?'prompt':'err';lastErr=e&&e.message||String(e);}showSaved();}
async function readFile(){const f=await FH.getFile();if(!f.size)return null;const j=JSON.parse(await f.text());return (j.autosave&&j.local&&(!j.report_id||j.report_id===RID))?j:null;}
async function syncWithFile(){try{const j=await readFile();const la=localAt();
  if(j&&(!la||String(j.local.saved_at)>la)){restoreLocal(j.local);lastFileAt=j.local.saved_at;}   /* file is newer → load it */
  else{FSTATE='ok';await writeFile();}                                                         /* browser is newer → update file */
  FSTATE='ok';}catch(e){FSTATE='err';lastErr=e.message;}showSaved();}
async function linkFile(){try{FH=await window.showSaveFilePicker({suggestedName:'decisions-'+RID+'.json',types:[{description:'JSON',accept:{'application/json':['.json']}}]});
  await idbSet(FH);FSTATE='ok';await syncWithFile();}catch(e){if(e&&e.name!=='AbortError'){lastErr=e.message;alert('Could not set up the save file: '+e.message);}}showSaved();}
async function reconnect(){if(!FH)return linkFile();try{const p=await FH.requestPermission({mode:'readwrite'});if(p==='granted'){FSTATE='ok';await syncWithFile();}else FSTATE='prompt';}catch(e){FSTATE='err';lastErr=e.message;}showSaved();}
async function unlinkFile(){if(!confirm('Stop auto-saving to '+(FH&&FH.name)+'? The file is kept; your progress stays in this browser.'))return;FH=null;FSTATE='none';await idbSet(null);showSaved();}
function showSaved(){const el=document.getElementById('rsave');if(!el)return;const la=localAt();let h='';
 if(!FH)h=`<span class="chip" title="Saved in this browser's storage. It is restored when you reopen this file in the same browser.">💾 Saved in browser${la?' · '+hm(la):''}</span>`+
  (FS?`<button class="sec" onclick="linkFile()" title="Also write every change to a JSON file on disk, so progress survives clearing browser data">Auto-save to file…</button>`
     :`<span class="muted" title="This browser cannot write files directly. Use Export decisions as a backup; Import can restore it.">(use Export as backup)</span>`);
 else if(FSTATE==='ok')h=`<span class="chip ok" title="Every change is written to ${esc(FH.name)} and to browser storage">💾 Auto-saved · ${esc(FH.name)}${lastFileAt?' · '+hm(lastFileAt):''}</span><a href="#" onclick="unlinkFile();return false" class="muted" style="font-size:12px">stop</a>`;
 else h=`<button style="background:#c62828" onclick="reconnect()" title="${esc(lastErr||'The browser needs your OK again to write to the save file')}">🔁 Reconnect save file (${esc(FH.name)})</button><span class="chip" title="Still saved in this browser">💾 Browser · ${hm(la)}</span>`;
 el.innerHTML=h;}
const _saveImports=saveImports;saveImports=function(){_saveImports();touched();};
document.addEventListener('change',e=>{if(e.target.closest('.decision'))touched();});
document.addEventListener('input',e=>{if(e.target.tagName==='TEXTAREA'||e.target.id==='by')touched();});
window.addEventListener('load',async()=>{try{navigator.storage&&navigator.storage.persist&&navigator.storage.persist();}catch(e){}
 if(FS){FH=await idbGet();if(FH){let p='prompt';try{p=await FH.queryPermission({mode:'readwrite'});}catch(e){}if(p==='granted'){FSTATE='ok';await syncWithFile();}else FSTATE='prompt';}}
 showSaved();});
window.addEventListener('beforeunload',()=>{if(wTimer){clearTimeout(wTimer);writeFile();}});
"""


def quality_section(d, items):
    if not QUAL:
        return ('<h2 id="quality">Quality &amp; risk</h2><p class="muted">Not scanned yet. Run '
                '<code>python3 "$SKILL_DIR/scripts/quality_scan.py" &lt;report&gt;/analysis.json</code> and re-render to get the file risk '
                'scores, SwiftLint on merged lines, test hints and the dependency diff.</p>')
    files = QUAL.get("files") or {}
    rows = []
    for f, v in sorted(files.items(), key=lambda kv: -kv[1]["score"]):
        parts = v.get("parts") or {}
        tip = " · ".join(f"{k} {n}" for k, n in parts.items())
        rows.append(f'<tr><td><code>{esc(f)}</code><div class="muted">{esc(v.get("area"))}</div></td>'
                    f'<td><div class="score lv-{esc(v["level"])}" title="{esc(tip)}"><i style="width:{v["score"]}%"></i><span>{v["score"]}</span></div></td>'
                    f'<td><span class="qchip lv-{esc(v["level"])}">{esc(v["level"]).upper()}</span></td>'
                    f'<td>{v["commits"]} commits · {v["authors"]} authors <span class="muted">({v["days"]} d)</span></td>'
                    f'<td>{"✓ function" if v["tested"] == "function" else "type only" if v["tested"] else "<b class=warn>none</b>"}</td>'
                    f'<td>{esc(v["sensitive"])}</td><td>{" ".join(f"<a class=dep href=#{esc(i)}>{esc(i)}</a>" for i in v["items"])}</td></tr>')
    h = ('<h2 id="quality">Quality &amp; risk</h2>'
         f'<p class="muted">From <code>quality_scan.py</code> at {esc(QUAL.get("generated_at"))} on <code>{esc(QUAL.get("tree"))}</code>. '
         'Risk score 0–100 = recent churn (20) + distinct authors (15) + no tests (20) + sensitive area (20) + item severity (15) + number of items (10). '
         'Hover a bar for the parts.</p>'
         '<h3>File risk</h3><table class="list"><tr><th>File</th><th style="width:170px">Score</th><th>Level</th><th>Churn on target</th>'
         '<th>Tests</th><th>Sensitive</th><th>Items</th></tr>' + "".join(rows) + "</table>")
    lint = QUAL.get("lint") or {}
    if lint.get("status") == "ok":
        lr = []
        for f, v in lint.get("files", {}).items():
            for x in v["new"]:
                lr.append(f'<tr class="{"hot" if x.get("items") else ""}"><td><code>{esc(os.path.basename(f))}</code>:{x["line"]}</td><td>{esc(x["rule"])}</td>'
                          f'<td>{esc(x["severity"])}</td><td>{esc(x["reason"])}<div class="muted"><code>{esc(x["text"][:140])}</code></div></td>'
                          f'<td>{" ".join(f"<a class=dep href=#{esc(i)}>{esc(i)}</a>" for i in x.get("items") or []) or "<span class=muted>nearby</span>"}</td></tr>')
        h += (f'<h3>SwiftLint — new after the merge ({lint["new_total"]}, {lint["on_merged_lines"]} on merged lines)</h3>'
              f'<p class="muted">SwiftLint {esc(lint.get("tool"))} · config: {esc(lint.get("config"))}. Each changed file is linted in the merged tree and at target HEAD; '
              'only warnings that did not exist before are listed. Highlighted rows sit on lines the merge brought in.</p>'
              + ('<table class="list"><tr><th>Where</th><th>Rule</th><th>Severity</th><th>Message</th><th>Item</th></tr>' + "".join(lr) + "</table>" if lr else "<p>No new warnings. ✓</p>"))
    else:
        h += f'<h3>SwiftLint</h3><p class="muted">{esc(lint.get("status") or "not run")}</p>'
    peri = QUAL.get("periphery") or {}
    if peri.get("status") == "ok":
        pu = peri.get("unused_in_changed_files") or []
        h += (f'<h3>Unused code (Periphery) in changed files ({len(pu)})</h3>' + ("<ul>" + "".join(
            f'<li><code>{esc(x["file"])}</code> {esc(x.get("kind"))} <b>{esc(x.get("name"))}</b> {esc(x.get("hint"))}</li>' for x in pu) + "</ul>" if pu else "<p>None. ✓</p>"))
    else:
        h += f'<h3>Unused code (Periphery)</h3><p class="muted">{esc(peri.get("status"))}</p>'
    qi = QUAL.get("items") or {}
    trows = []
    for it in items:
        if it["id"] not in qi:
            continue
        t = qi[it["id"]].get("tests") or []
        fn = [x for x in t if x["kind"] == "function"]
        trows.append((0 if fn else 1 if t else 2, it["id"],
                      f'<tr><td><a class="dep" href="#{esc(it["id"])}">{esc(it["id"])}</a></td><td><code>{esc(", ".join(qi[it["id"]].get("symbols") or []))}</code></td><td>'
                      + ("<br>".join(f'<code>{esc(x["file"])}</code> <span class="muted">({esc(x["kind"])}: {esc(", ".join(x["names"]))})</span>' for x in t)
                         or '<b class="warn">no test references</b>') + "</td></tr>"))
    nt = sum(1 for r in trows if r[0] == 2)
    h += (f'<details><summary>Test impact — {len(trows) - nt} items referenced by tests, {nt} with none ({QUAL.get("test_files", 0)} test files scanned)</summary>'
          '<p class="muted">A test that calls the changed function is a real hint; one that only names the type is weak. Coverage % is not measured.</p>'
          '<table class="list"><tr><th>Item</th><th>Changed symbols</th><th>Tests that reference them</th></tr>'
          + "".join(r[2] for r in sorted(trows, key=lambda r: (-r[0], r[1]))) + "</table></details>")
    deps = QUAL.get("dependencies") or []
    miss = QUAL.get("build_missing_modules") or []
    drows = []
    for df in deps:
        for r in df["rows"]:
            bad = "differ" in r["change"] or "neither" in r["change"]
            drows.append(f'<tr class="{"hot" if bad else ""}"><td>{esc(df["kind"])}</td><td><b>{esc(r["name"])}</b></td><td>{esc(r["base"] or "—")}</td>'
                         f'<td>{esc(r["source"] or "—")}</td><td>{esc(r["target"] or "—")}</td><td>{esc(r["merged"] or "—")}</td><td>{esc(r["change"])}</td></tr>')
    h += (f'<h3>Dependencies ({len(drows)} pins differ)</h3>'
          + ('<table class="list"><tr><th>Manager</th><th>Package</th><th>Base</th><th>Source</th><th>Target</th><th>Merged tree</th><th>Change</th></tr>'
             + "".join(drows) + "</table>" if drows else '<p class="muted">No package pins differ between base, source and target.</p>')
          + ('<div class="esc"><b>Build logs could not resolve these modules:</b> '
             + ", ".join(f'<code>{esc(m["module"])}</code> <span class="muted">({esc(", ".join(m["logs"]))})</span>' for m in miss)
             + ' — usually package resolution or a scheme that does not link the package, not merged code. Check the pins above and re-run '
               '<code>xcodebuild -resolvePackageDependencies</code>.</div>' if miss else ""))
    return h


def main():
    path = sys.argv[1]
    d = json.load(open(path))
    folder = os.path.dirname(os.path.abspath(path))
    qp = os.path.join(folder, "quality.json")
    if os.path.exists(qp):
        try:
            QUAL.update(json.load(open(qp)))
        except (OSError, json.JSONDecodeError) as e:
            print(f"WARNING: quality.json unreadable: {e}")
    for bp in sorted(glob.glob(os.path.join(folder, "review-queue", "batch_*.results.json"))):
        try:
            bj = json.load(open(bp))
        except (OSError, json.JSONDecodeError):
            continue
        name = (bj.get("reviewer") or os.path.basename(bp)[6:-13]).replace("batch-", "").replace("_", " ")
        for x in bj.get("items") or []:
            if x.get("id"):
                BATCH.setdefault(x["id"], name)
    rid = d["report_id"]
    items = d["items"]
    need_all = sorted([i for i in items if i["needs_decision"]], key=lambda i: (SEV_ORDER.get(i["severity"], 9), i["file"]))
    recheck = [i for i in need_all if not i.get("decision") and i.get("recheck") and not i.get("escalated")] + \
              sorted([i for i in items if not i["needs_decision"] and i.get("recheck")], key=lambda i: i["file"])
    recheck_ids = {i["id"] for i in recheck}
    need = [i for i in need_all if not i.get("decision") and i["id"] not in recheck_ids]   # escalated / still open
    ai_decided = [i for i in need_all if i.get("decision") and i.get("decided_by") == "ai"]
    dev_decided = [i for i in need_all if i.get("decision") and i.get("decided_by") != "ai"]
    review = sorted([i for i in items if not i["needs_decision"] and i["id"] not in recheck_ids and (i.get("ai_category") or i["category"]) in
                     ("NEAR_CHANGE", "RESTRUCTURED", "OPTIMIZED_IN_TARGET", "OPTIMIZED_IN_SOURCE", "NEW_FILE", "BINARY", "PROJECT_FILE",
                      "VENDORED_BUNDLE", "MAPPING_UNCERTAIN", "NEW_SYMBOL", "SYMBOL_NOT_FOUND")],
                    key=lambda i: i["file"])
    carded = {i["id"] for i in review} | {i["id"] for i in need_all} | recheck_ids   # every item shown once
    auto = [i for i in items if i["id"] not in carded]
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
    rr = d.get("repo_risks") or []
    order = {"block": 0, "warn": 1, "info": 2}
    repo_risks_html = ""
    if rr:
        lis = "".join(
            f'<li><span class="lv {esc(x["level"])}">{esc({"block": "NEEDS ACTION", "warn": "CHECK", "info": "INFO"}[x["level"]])}</span>'
            f'<b>{esc(x["code"])}</b> — {esc(x["message"])}'
            + ("".join(f' <a href="#{esc(i)}" class="dep">{esc(i)}</a>' for i in (x.get("items") or [])[:12]))
            + (f' <label class="confirm"><input type="checkbox" class="rack" data-ack="{esc(x["code"])}-{n}"> acknowledged / handled</label>' if x["level"] == "block" else "")
            + "</li>" for n, x in enumerate(sorted(rr, key=lambda x: order.get(x["level"], 9))))
        repo_risks_html = (f'<div id="repo-risks"><h3 style="margin:4px 0">Repository risks ({len(rr)})</h3><p class="muted" style="margin:2px 0">'
                           'Found by risk_scan.py across the whole repository. “Needs action” items block the merge until a person ticks them.</p><ul>' + lis + '</ul></div>')
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
    auto_rows = "".join(f'<tr><td><a href="#{esc(i["id"])}">{esc(i["id"])}</a></td><td>{badge(i.get("ai_category") or i["category"])}</td><td><code>{esc(i["file"])}</code>'
                        f'{(" → <code>" + esc(i["target_path"]) + "</code>") if i.get("target_path") and i["target_path"] != i["file"] else ""}</td>'
                        f'<td>{esc((i.get("source") or {}).get("start", ""))}</td><td>{esc(", ".join(a.get("name", "") + " " + a.get("date", "") for a in i.get("source_authors", [])[:2]))}</td>'
                        f'<td>{esc(i.get("decision") or "take source (git)")}</td></tr>'
                        for i in auto)
    paths = "".join(f'<tr><td><code>{esc(f["source_path"])}</code></td><td>{esc(f["source_status"])}</td><td><code>{esc(f["target_path"] or "— not found —")}</code></td>'
                    f'<td>{esc(f["mapping"]["method"])}</td><td>{esc(f["mapping"]["confidence"])}</td><td>{"🔒" if f["protected"] else ""}</td></tr>'
                    for f in d["files"])
    tgt_only = "".join(f'<tr><td>{esc(x["status"])}</td><td><code>{esc(x["path"])}</code></td></tr>' for x in d.get("target_only_changes", [])[:400])

    quality_html = quality_section(d, items)
    areas = sorted({area_of(i) for i in items if i["id"] in carded}, key=str.lower)

    applied = {}
    for i in items:
        for n in i.get("reviewed_by_developer") or []:
            x = applied.setdefault(n, {"name": n, "decisions": 0, "changed": 0, "confirmed": 0})
            x["decisions"] += 1
            x["changed" if i.get("decided_by") == "developer" else "confirmed"] += 1
    dm = d.get("decisions_meta") or {}
    meta = {"applied": sorted(applied.values(), key=lambda x: -x["decisions"]), "files": [os.path.basename(s) for s in dm.get("sources") or []],
            "applied_at": dm.get("loaded_at"), "auto": len(auto)}
    meta_js = "const REPORT_META=" + json.dumps(meta).replace("</", "<\\/") + ";"
    page = f'''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Merge report {esc(s["branch"])} → {esc(t["branch"])} · {esc(rid)}</title><style>{CSS}{TRACKER_CSS}</style></head><body>
<div class="bar"><b>{esc(rid)}</b><span id="progress"></span><input id="by" placeholder="Decided by (your name)"><button onclick="exportJson()">Export decisions (.json)</button>
{TRACKER_BAR}<select id="rrisk" title="Filter by risk"><option value="">Risk: any</option>{"".join(f'<option value="{k}">Risk: {v}</option>' for k, v in {**RISK_LABELS, **QUAL_LABELS}.items())}</select><select id="rarea" title="Filter by feature area"><option value="">Area: all</option>{"".join(f'<option value="{esc(a)}">Area: {esc(a)}</option>' for a in areas)}</select><button onclick="window.print()" style="background:#455a64">Print / PDF</button><button class="sec" id="themebtn" onclick="cycleTheme()" title="Theme: auto / light / dark">◐ Auto</button><button class="sec" onclick="toggleHelp()" title="Keyboard shortcuts (?)">⌨ ?</button><nav><a href="#tracker">Tracker</a><a href="#quality">Quality</a><a href="#decide">Decisions</a><a href="#review">Review</a><a href="#auto">Auto-applied</a><a href="#paths">Path map</a><a href="#commits">Commits</a></nav><div id="pbar"><i></i></div></div>
<div id="minimap" aria-label="Card map"></div>
<div id="khelp" hidden><b>Keyboard</b><table>
<tr><td><kbd>j</kbd> / <kbd>k</kbd></td><td>next / previous card</td></tr><tr><td><kbd>n</kbd></td><td>next pending card</td></tr>
<tr><td><kbd>s</kbd> <kbd>t</kbd> <kbd>b</kbd> <kbd>a</kbd> <kbd>c</kbd></td><td>choose Source / Target / Both / AI / Custom</td></tr>
<tr><td><kbd>Enter</kbd></td><td>accept the AI recommendation (★)</td></tr><tr><td><kbd>r</kbd></td><td>toggle “Mark reviewed”</td></tr>
<tr><td><kbd>e</kbd></td><td>write notes (Esc to leave)</td></tr><tr><td><kbd>l</kbd></td><td>copy a link to the card</td></tr>
<tr><td><kbd>g</kbd></td><td>jump to the first evidence line</td></tr><tr><td><kbd>d</kbd></td><td>toggle dark mode</td></tr><tr><td><kbd>?</kbd></td><td>this help</td></tr></table></div>
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
<div class="resume"><b>How to continue.</b> 1) Each developer filters the report to their name (<b>Developer</b> dropdown), picks a decision on every card under “Needs you” (★ = AI recommendation), adds notes, or ticks <b>Mark reviewed</b>. The <b>Tracker</b> shows reviewed / pending per card and the <b>Ready to merge</b> chip lists what still blocks the merge.
Progress is kept in the browser; in Chrome/Edge click <b>Auto-save to file…</b> and save <code>decisions-{esc(rid)}.json</code> into the report folder so it also survives clearing browser data.
2) Click <b>Export decisions</b> and save the file into the report folder (or edit <code>report.md</code> checkboxes). The merge owner can <b>Import</b> several developers' files at once; disagreements are flagged and must be settled before merging. 3) In the same chat{(" (" + esc(g.get("session_id")) + ")") if g.get("session_id") else ""}, or any new chat with this skill, say:<br>
<code id="resumecmd">{esc(resume_cmd)}</code> <button onclick="copyResume()" style="margin-left:8px">Copy</button>
{("<br>Resume hint: <code>" + esc(g.get("resume_hint")) + "</code>") if g.get("resume_hint") else ""}</div>

<details open><summary>How to read a card</summary><ul>
<li><b>Base (common ancestor)</b> — the code as it was at the last commit both branches share (<code>{esc((d["analysis_base"] or "")[:12])}</code>), i.e. before either branch changed it. Red lines = what was there and got changed.</li>
<li><b>Source — incoming</b> — the same code on <code>{esc(s["branch"])}</code> now (what the merge brings). Green = changed by source.</li>
<li><b>Target — current</b> — the same code on <code>{esc(t["branch"])}</code> now (what you have). Amber = changed by target.</li>
<li>The purple name next to a line is the developer who wrote that exact line (on Base: who removed it). The "Who to talk to" table lists only those people.</li>
<li><b>Options:</b> "Replace with source code as-is" really replaces target's version — if target refactored or optimised that code, its improvements are lost. To keep the source fix <i>and</i> target's design, pick "Source behaviour inside target code".</li>
<li>Comparing Source and Target with Base shows who changed what: if only one side differs from Base, take that side; if both differ, a person decides.</li></ul></details>
{structure_html}
{repo_risks_html}
<h2>Summary</h2>
<div class="tiles"><div class="tile"><div class="n">{d["summary"]["needs_decision"]}</div>decisions needed</div>
<div class="tile"><div class="n">{d["summary"]["items"]}</div>change items</div><div class="tile"><div class="n">{d["summary"]["source_commits"]}</div>source commits</div>
<div class="tile"><div class="n">{d["summary"]["files_changed_in_source"]}</div>files changed in source</div>{tiles}</div>
{"<p class='warn'><b>Warning:</b> AI review missing for " + ", ".join(missing_ai) + "</p>" if missing_ai else ""}
<h3>Who to talk to — exact authors of the conflicting lines</h3>
<p class="muted">Only the developers who wrote (or removed) the exact lines in each decision item — taken line by line from git blame, not from who else touched the file.</p>
<table class="list"><tr><th>Item</th><th>Type</th><th>File</th><th>Incoming lines written by</th><th>Current lines written by</th></tr>{talk or '<tr><td colspan="5">No decisions needed.</td></tr>'}</table>
<h3>Per developer</h3><table class="list"><tr><th>Developer</th><th>Email</th><th>Decision items (side)</th></tr>{devs or '<tr><td colspan="3">—</td></tr>'}</table>
{quality_html}
<div id="areas"></div>

<div id="tracker"></div>
{TRACKER_DIALOG}
{("<h2 id='recheck'>AI re-check pending (" + str(len(recheck)) + ")</h2><p class='muted'>The AI's own review is incomplete here (weak second check, or a look-alike in a parallel module not checked yet). The agent must finish these before the merge; a developer may also decide them.</p><div class='need'>" + "".join(item_card(i) for i in recheck) + "</div>") if recheck else ""}
<h2 id="decide">Needs you ({len(need)})</h2><div class="need">{"".join(item_card(i) for i in need) or "<p>Nothing — the AI decided every item from the code; see below. Override any card before the commit if you disagree.</p>"}</div>
{("<h2 id='aidecided'>Decided by AI (" + str(len(ai_decided)) + ")</h2><p class='muted'>Each was reviewed from the code logic, with evidence and (for high-severity items) an independent second check. Change any option to override.</p><details><summary>Show " + str(len(ai_decided)) + " AI decisions</summary><div class='need'>" + "".join(item_card(i) for i in ai_decided) + "</div></details>") if ai_decided else ""}
{("<h2 id='devdecided'>Decided by developer (" + str(len(dev_decided)) + ")</h2><div class='need'>" + "".join(item_card(i) for i in dev_decided) + "</div>") if dev_decided else ""}
<h2 id="review">Review — merges, but check the logic ({len(review)})</h2>
<p class="muted">These do not block the merge. The pre-selected option is the AI's decision (★ = its recommendation); without one, git takes source. Change it only if you disagree.</p>
<div class="review">{"".join(item_card(i) for i in review) or "<p>None.</p>"}</div>
<h2 id="auto">Auto-applied changes ({len(auto)})</h2>
<p class="muted">Every remaining source change (not shown as a card above), listed so nothing is merged unseen. Flag any by adding it to the notes of a decision or telling the merge owner.</p>
<details><summary>Show all {len(auto)} items</summary><table class="list"><tr><th>ID</th><th>Category</th><th>File</th><th>Line</th><th>Author</th><th>Decision</th></tr>{auto_rows}</table>
{"".join(item_card(i, decision_ui=False) for i in auto)}</details>
<h2 id="paths">File / path map ({len(d["files"])})</h2><details><summary>Show</summary><table class="list"><tr><th>Source path</th><th>Status</th><th>Target path</th><th>Method</th><th>Confidence</th><th>Protected</th></tr>{paths}</table></details>
<h2 id="commits">Source commits ({len(d["commits"])})</h2><details><summary>Show</summary><table class="list"><tr><th>Commit</th><th>Date</th><th>Author</th><th>Subject</th><th></th></tr>{commits}</table></details>
<h2>Changed only in target ({len(d.get("target_only_changes", []))})</h2><details><summary>Show</summary><p class="muted">Not touched by the merge; listed for context.</p><table class="list">{tgt_only}</table></details>
<p class="muted" style="margin-top:30px">Generated by the safe-branch-merge skill · {esc(rid)}</p>
</div><script>{JS % {"rid": json.dumps(rid)}}{meta_js}{TRACKER_JS}</script></body></html>'''
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
        if it.get("depends_on"):
            out.append("- Depends on: " + ", ".join(it["depends_on"]))
        if it.get("doubt_cleared"):
            out.append(f"- ⚠ Earlier doubt cleared (was {it['doubt_cleared']}); reason: {it.get('change_reason') or 'none'}")
        if it.get("counterparts"):
            out.append("- Look-alike in parallel module: " + ", ".join(f"`{c['path']}`" for c in it["counterparts"])
                       + (f" — verdict: {it.get('counterpart_verdict')} ({it.get('counterpart_note') or ''})" if it.get("counterpart_verdict") else " — not checked yet"))
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

    if recheck:
        md += ["", f"## AI re-check pending ({len(recheck)}) — the agent must finish these", ""]
        for it in recheck:
            md += [f"- **{it['id']}** `{it['file']}` — " + "; ".join(it.get("recheck") or [])]
            md += md_item(it)
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
