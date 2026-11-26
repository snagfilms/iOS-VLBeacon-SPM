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
DEFAULT_LABELS = {"SOURCE": "Use incoming change", "TARGET": "Keep current code (drop incoming change)",
                  "BOTH": "Keep both", "AI": "Use AI's merged version",
                  "CUSTOM": "Custom — describe in notes"}
CAT_HUMAN = {
    "CONFLICT": "Both sides changed", "MAPPING_UNCERTAIN": "File location unclear", "SYMBOL_NOT_FOUND": "Function gone in current",
    "NEW_SYMBOL": "New function", "VENDORED_BUNDLE": "Bundled framework", "DELETED_IN_TARGET": "File removed in current",
    "DELETED_IN_SOURCE": "File removed in incoming", "PROTECTED": "Branch-specific file", "PROJECT_FILE": "Xcode project change",
    "RESTRUCTURED": "File moved in current", "OPTIMIZED_IN_TARGET": "Current was refactored", "OPTIMIZED_IN_SOURCE": "Incoming was refactored",
    "NEW_FILE": "New file", "NEAR_CHANGE": "Merges, check nearby code", "BINARY": "Binary file", "LARGE_FILE": "Very large file",
    "CLEAN": "Only incoming changed", "ALREADY_PRESENT": "Already in current", "COSMETIC": "Formatting only", "GENERATED": "Generated code",
    "TOOLING": "Editor / AI config", "JUNK": "OS / user file", "IB_METADATA": "Interface Builder metadata"}
NEEDS_LOOK_CATS = {"CONFLICT", "MAPPING_UNCERTAIN", "SYMBOL_NOT_FOUND", "DELETED_IN_TARGET", "DELETED_IN_SOURCE", "PROTECTED",
                   "OPTIMIZED_IN_TARGET", "OPTIMIZED_IN_SOURCE", "NEAR_CHANGE", "RESTRUCTURED", "PROJECT_FILE", "VENDORED_BUNDLE"}
GLOSSARY = {
    "base": "Base = the code as it was at the last commit both branches share, before either side changed it.",
    "incoming": "Incoming = the branch you merge FROM (source). Green lines are what it changed.",
    "current": "Current = the branch you merge INTO (target), as it is now. Amber lines are what it changed.",
    "result": "Result = what the file will contain with the AI's merged version.",
    "confidence": "How sure the AI is: 90%+ proven from code or history, 80-90% strong reading, below 80% a person decides.",
    "check": "A second, independent review of the same item that tried to prove the opposite choice.",
    "risk": "File risk 0-100: recent changes, number of authors, missing tests, sensitive area (ads, analytics, payments) and how many items touch it.",
    "lookalike": "A look-alike is a file in a parallel module (e.g. ViewliftOne) that implements the same screen or service and may need the same change.",
    "reviewed": "Reviewed = someone picked an option, wrote a note, or ticked Mark reviewed. A pre-selected AI option alone does not count.",
}


def tip(key):
    return f'<span class="tip" tabindex="0" data-tip="{esc(GLOSSARY[key])}" aria-label="{esc(GLOSSARY[key])}">?</span>'


def human(cat):
    return CAT_HUMAN.get(cat, cat.replace("_", " ").title())
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

# ================================================================ commit links (GitHub / GitLab / Bitbucket / Azure DevOps / custom)
import subprocess as _sp
REPOS = {}        # side -> {"path": repo path, "tmpl": "https://host/o/r/commit/{sha}" or None, "host": "GitHub"}
KNOWN_SHAS = {}   # full sha -> side, for linking commit ids that appear in free text
_PUSHED = {}


def _git(repo, *a):
    try:
        p = _sp.run(["git", "-C", repo, *a], capture_output=True, text=True, timeout=20)
        return p.stdout.strip() if p.returncode == 0 else ""
    except (OSError, _sp.TimeoutExpired):
        return ""


def commit_template(remote):
    """Web URL template for a commit, from a git remote URL (https, ssh or scp-style)."""
    r = (remote or "").strip()
    m = re.match(r"^(?:ssh://)?(?:[^@/]+@)?([^:/]+)(?::\d+)?[:/](.+?)(?:\.git)?/?$", r) if not r.startswith("http") else \
        re.match(r"^https?://(?:[^@/]+@)?([^/]+)/(.+?)(?:\.git)?/?$", r)
    if not m:
        return None, None
    host, path = m.group(1).lower(), m.group(2).strip("/")
    if host.startswith("ssh.dev.azure.com") or host.endswith("vs-ssh.visualstudio.com"):
        parts = path.split("/")                                   # v3/org/project/repo
        if len(parts) >= 4:
            return f"https://dev.azure.com/{parts[1]}/{parts[2]}/_git/{parts[3]}/commit/{{sha}}", "Azure DevOps"
    if host == "dev.azure.com" or host.endswith(".visualstudio.com"):
        return f"https://{host}/{path}/commit/{{sha}}", "Azure DevOps"
    if "bitbucket" in host:
        return f"https://{host}/{path}/commits/{{sha}}", "Bitbucket"
    if "gitlab" in host:
        return f"https://{host}/{path}/-/commit/{{sha}}", "GitLab"
    name = "GitHub" if "github" in host else host
    return f"https://{host}/{path}/commit/{{sha}}", name   # GitHub, GitHub Enterprise, Gitea, Forgejo use /commit/


def setup_commit_links(d):
    for side in ("source", "target"):
        info = d.get(side) or {}
        repo = info.get("repo_root") or info.get("folder")
        cfg = {}
        try:
            cfg = json.load(open(os.path.join(repo, ".merge-guard.json"))) if repo else {}
        except (OSError, json.JSONDecodeError):
            cfg = {}
        tmpl, host = (cfg.get("commit_url"), "repository") if cfg.get("commit_url") else (None, None)
        if not tmpl and repo:
            remote = _git(repo, "remote", "get-url", "origin") or (_git(repo, "remote", "-v").split() or ["", ""])[1:2][0] if _git(repo, "remote") else ""
            tmpl, host = commit_template(remote)
        REPOS[side] = {"path": repo, "tmpl": tmpl, "host": host or "repository"}
    for c in d.get("commits") or []:
        KNOWN_SHAS.setdefault(c.get("sha") or "", "source")
    for it in d.get("items") or []:
        for key, side in (("source_authors", "source"), ("target_authors", "target")):
            for p in it.get(key) or []:
                if p.get("sha"):
                    KNOWN_SHAS.setdefault(p["sha"], side)
                o = p.get("ported_from") or {}
                if o.get("sha"):
                    KNOWN_SHAS.setdefault(o["sha"], side)
    KNOWN_SHAS.pop("", None)


def pushed(side, sha):
    """True when a remote-tracking branch contains the commit (else the web link would 404)."""
    key = (side, sha)
    if key not in _PUSHED:
        repo = (REPOS.get(side) or {}).get("path")
        out = _git(repo, "branch", "-r", "--contains", sha) if repo else ""
        if not out and side == "source":               # the target clone may know it too
            other = (REPOS.get("target") or {}).get("path")
            out = _git(other, "branch", "-r", "--contains", sha) if other else ""
        _PUSHED[key] = bool(out)
    return _PUSHED[key]


def commit_url(sha, side="source"):
    r = REPOS.get(side) or REPOS.get("source") or {}
    if not sha or not r.get("tmpl") or len(sha) < 7:
        return None
    if len(sha) < 40:                                   # expand a short id we know
        full = next((k for k in KNOWN_SHAS if k.startswith(sha)), None)
        if full:
            sha, side = full, KNOWN_SHAS[full]
            r = REPOS.get(side) or r
    if not pushed(side, sha):
        return None
    return r["tmpl"].replace("{sha}", sha)


def clink(short, sha=None, side="source", code=True):
    """A commit id that opens the commit on the git host (new tab); plain text when it can't be linked."""
    sha = sha or short
    label = f"<code>{esc(short)}</code>" if code else esc(short)
    u = commit_url(sha, side)
    if not u:
        why = "not pushed to the remote yet" if (REPOS.get(side) or {}).get("tmpl") else "no git remote to link to"
        return f'<span class="sha nolink" title="{esc(sha)} — {why}">{label}</span>'
    host = (REPOS.get(KNOWN_SHAS.get(sha, side)) or REPOS.get(side) or {}).get("host", "repository")
    return f'<a class="sha" href="{esc(u)}" target="_blank" rel="noopener noreferrer" title="Open commit {esc(sha[:12])} on {esc(host)}">{label}</a>'


_SHA_RX = re.compile(r"(?<![\w/#.-])([0-9a-f]{7,40})(?![\w-])")


def link_shas(html_text):
    """Link commit ids of this merge that appear in already-escaped text (AI analysis, evidence, risks …)."""
    if not KNOWN_SHAS:
        return html_text

    def sub(m):
        x = m.group(1)
        full = next((k for k in KNOWN_SHAS if k.startswith(x)), None)
        return clink(x, full, KNOWN_SHAS[full], code=False) if full else x
    parts = re.split(r"(<[^>]+>)", html_text)              # never touch tags / attributes
    return "".join(p if p.startswith("<") else _SHA_RX.sub(sub, p) for p in parts)


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


FPS = {}       # card fingerprints (render-state.json)
SRC_BRANCH, TGT_BRANCH = "source", "target"
VERIFY = {}    # verification.json results by item id
RES_COL = ('<div class="c-res"><h5>Result — AI\'s merged version <span class="tip" tabindex="0" data-tip="What the file will contain for the option you pick. '
           'Shown only when the AI wrote merged code that differs from both sides.">?</span></h5><div class="resbody"><div class="code empty">Pick an option to preview the result.</div></div></div>')
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


def verify_chip(it):
    v = VERIFY.get(it["id"]) or {}
    st = (v.get("status") or "")
    if v.get("missing"):
        return (f'<span class="qchip block" title="{esc("; ".join(v["missing"][:4]))}">✗ {len(v["missing"])} incoming line'
                f'{"s" if len(v["missing"]) > 1 else ""} missing after merge</span>')
    if st.startswith("CHECK"):
        return '<span class="qchip look" title="Lines were rewritten by the merge — confirm the business logic is kept">verify: check rewritten lines</span>'
    if v.get("still_present"):
        return (f'<span class="qchip look" title="{esc("; ".join(v["still_present"][:4]))}">{len(v["still_present"])} removed line'
                f'{"s" if len(v["still_present"]) > 1 else ""} still present</span>')
    return ""


def chip_row(it):
    """Status chips: blocking first, then needs-a-look, then info. The page shows 3 and folds the rest behind “+N”."""
    q = quality_chips(it)
    inner = q[len('<div class="qrow">'):-len("</div>")] if q else ""
    chips = verify_chip(it) + risk_chips(it) + inner + history_chips(it)
    return f'<div class="qrow">{chips}</div>' if chips else ""


def verdict_line(it, lab, decision_ui):
    rec, conf = it.get("recommended_option"), it.get("ai_confidence")
    cv = (it.get("check_verdict") or "").lower()
    first = re.split(r"(?<=[.!?])\s", (it.get("ai_recommendation") or "").strip())[0][:220]
    if rec:
        sure = f' · <b>{int(round(conf * 100))}%</b> sure' if conf is not None else ""
        chk = (' · checked ✓' if cv.startswith("agree") else ' · <span class="v-look">second check disagrees</span>' if cv else
               ' · <span class="muted">no second check</span>')
        return f'<div class="verdict">🤖 AI suggests <b>{esc(lab.get(rec, rec))}</b>{sure}{chk}<div class="muted">{esc(first)}</div></div>'
    if it.get("needs_decision") and not it.get("ai_recommendation"):
        return '<div class="verdict v-look">🤖 AI review still pending for this item.</div>'
    if not decision_ui:
        return f'<div class="verdict muted">Applied automatically — {esc(CAT_INFO.get(it.get("ai_category") or it["category"], ("", ""))[1])}</div>'
    return f'<div class="verdict muted">{esc(first)}</div>' if first else ""


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


def person(p, with_commit=True, side="source"):
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
        port = (f'<div class="muted">↳ ported/cherry-picked from {clink(o["short"], o.get("sha"), side)} by <b>{esc(o["name"])}</b> '
                f'&lt;{esc(o["email"])}&gt; {esc(o["date"])} — {esc(o["subject"])}</div>')
    commit = f' — {esc(p.get("date"))} — {clink(p.get("short"), p.get("sha"), side)} {esc(p.get("subject"))}' if with_commit else ""
    note = f' <span class="muted">({esc(p["note"])})</span>' if p.get("note") else ""
    return f'<div class="dev"><b>{esc(p.get("name"))}</b> &lt;{esc(p.get("email"))}&gt;{lines}{commit}{note}{port}</div>'


def people(lst, side="source"):
    if not lst:
        return '<span class="muted">—</span>'
    out = [person(p, side=side) for p in lst[:6]]
    if len(lst) > 6:
        out.append(f'<div class="muted">+{len(lst) - 6} more commit(s)</div>')
    return "".join(out)


def badge(cat):
    kind = "look" if cat in NEEDS_LOOK_CATS else "info"
    return f'<span class="badge b-{kind}" title="{esc(cat)} — {esc(CAT_INFO.get(cat, ("", ""))[1])}">{esc(human(cat))}</span>'


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


def risk_chips(it):
    return "".join(f'<span class="risk r-{k}">{esc(RISK_LABELS[k])}</span>' for k in risks_of(it))


def extras(it, with_risks=False):
    out = ""
    rk = risks_of(it) if with_risks else []
    if rk:
        out += '<div class="risks">' + "".join(f'<span class="risk r-{k}">{esc(RISK_LABELS[k])}</span>' for k in rk) + "</div>"
    if it.get("recheck"):
        out += '<div class="esc"><b>AI re-check pending:</b> ' + esc("; ".join(it["recheck"])) + "</div>"
    if it.get("doubt_cleared") and it.get("decided_by") != "developer":     # a person decided: the old doubt is settled
        out += (f'<div class="esc"><b>Earlier doubt cleared:</b> an earlier review said <b>{esc(it["doubt_cleared"])}</b>. '
                f'Reason given: {link_shas(esc(it.get("change_reason") or "none"))}</div>')
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
                       f'<td>{esc(x.get("check_verdict"))}</td><td>{link_shas(esc(x.get("change_reason") or ""))}</td></tr>' for x in h)
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
    signals = "".join(f"<li>{link_shas(esc(s))}</li>" for s in it.get("signals", []))
    summary = ""
    if it.get("summary_lines"):
        summary = '<pre class="summary">' + esc("\n".join(it["summary_lines"])) + "</pre>"
    snippets = ""
    terms, evl = evidence_terms(it)
    if any(it.get(k) for k in ("base", "source", "target")):
        aid = it["id"]
        snippets = f'''<div class="cols cols4">
  <div class="c-base"><h5>Base — before both {tip("base")}</h5>{code_block(it.get("base"), "del", terms, evl, aid + "-base")}</div>
  <div class="c-src"><h5>Incoming — {esc(SRC_BRANCH)} {tip("incoming")}</h5>{code_block(it.get("source"), "add", terms, evl, aid + "-source")}</div>
  <div class="c-tgt"><h5>Current — {esc(TGT_BRANCH)} {tip("current")}</h5>{code_block(it.get("target"), "chg", terms, evl, aid + "-target")}</div>
  {RES_COL if it.get("proposed_code") else ""}
</div>'''.replace('class="cols cols4"', 'class="cols cols4"' if it.get("proposed_code") else 'class="cols cols3"')
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
            why = (f'<div class="why"><div class="whyh"><b>Why the AI suggests “{esc(lab.get(rec, rec) if rec else "—")}”</b> {tip("confidence")}'
                   + (f'<span class="meter" title="confidence {esc(conf)}"><i style="width:{pct}%" class="{"hi" if pct >= 90 else "mid" if pct >= 80 else "lo"}"></i></span><b>{pct}%</b>' if conf is not None else "")
                   + (f'<span class="qchip {"ok" if cv.startswith("agree") else "bad"}">2nd check: {esc(it.get("check_verdict"))}{(" · " + esc(it.get("check_by"))) if it.get("check_by") else ""}</span>' if cv else '<span class="qchip warn">no independent check</span>')
                   + "</div>"
                   + ("<ul>" + "".join(f"<li>{link_shas(esc(b))}</li>" for b in bullets[:8]) + "</ul>" if bullets else "")
                   + ("<div class=\"evl\">Evidence in the code: " + " ".join(f'<a href="#{esc(a)}" class="dep" data-jump="1">{lb} L{n}</a>' for lb, a, n in hits[:16]) + "</div>" if hits else
                      "<div class=\"muted\" style=\"font-size:12px\">The evidence names no line shown in the snippets.</div>")
                   + "</div>")
        ai = f'''{why}<div class="ai"><h4>AI analysis</h4><p>{link_shas(esc(it.get("ai_analysis")).replace(chr(10), "<br>"))}</p>
<h4>AI recommendation{(": " + esc(lab.get(rec, rec))) if rec else ""}{(" · confidence " + esc(it.get("ai_confidence"))) if it.get("ai_confidence") is not None else ""}</h4><p>{link_shas(esc(it.get("ai_recommendation")).replace(chr(10), "<br>"))}</p>{prop}
{("<h5>Evidence</h5><p>" + link_shas(esc(it.get("ai_evidence"))) + "</p>") if it.get("ai_evidence") else ""}
{("<h5>Independent check: " + esc(it.get("check_verdict")) + "</h5><p>" + link_shas(esc(it.get("check_note") or "")) + "</p>") if it.get("check_verdict") else ""}</div>'''
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
    open_default = bool(it.get("escalated") or it.get("recheck") or (it.get("needs_decision") and not it.get("decision")))
    return f'''<section class="card sev-{esc(it["severity"])}{" open blocking" if open_default else ""}" id="{esc(it["id"])}" data-risk="{" ".join(risks_of(it) + qual_tokens(it))}" data-deps="{esc(" ".join(it.get("depends_on") or []))}" data-area="{esc(area_of(it))}" data-rec="{esc(it.get("recommended_option") or "")}" data-fp="{esc(FPS.get(it["id"], ""))}">
<header><a class="iid" href="#{esc(it["id"])}" title="Link to this card (click to copy)">{esc(it["id"])}</a>{badge(cat)}<span class="sev sev-{esc(it["severity"])}">{esc(it["severity"]).upper()}</span><span class="ttl">{esc(it["title"])}</span></header>
{verdict_line(it, lab, decision_ui)}
<div class="spath"><code>{esc(it.get("target_path") or it["file"])}</code></div>
{chip_row(it)}
{dec}
<button type="button" class="more-t" aria-expanded="false">Show details ▾</button>
<div class="more"><div class="path">{path_line}</div>{mapping}
<div class="devs"><div><h5>Incoming (source) — who wrote these exact lines</h5>{people(it.get("source_authors"), "source")}</div><div><h5>Current (target) — who wrote the conflicting lines</h5>{people(it.get("target_authors"), "target")}</div></div>
{"<ul class='signals'>" + signals + "</ul>" if signals else ""}{summary}{snippets}{ai}{aids_html(it)}{extras(it)}</div></section>'''


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


EXTRA_CSS = r"""
/* ---- review speed: 4-way columns, evidence rows, why panel, chips, syntax colours */
.cols.cols4{grid-template-columns:repeat(4,minmax(0,1fr))}@media (max-width:1300px){.cols.cols4{grid-template-columns:1fr 1fr}}
tr.ev td.lc{box-shadow:inset 3px 0 0 #7e57c2;background:#efe9ff!important}tr.ev td.ln{color:#5e35b1;font-weight:700}tr.flash td{animation:flash 1.6s}
@keyframes flash{0%{background:#ffe082}100%{background:inherit}}
.c-res .rlab{font-size:11px;color:#5b6775;margin:0 0 4px}.c-res .code{min-height:40px}
.why{background:#f8f5ff;border:1px solid #d9d0ff;border-left:4px solid #7e57c2;border-radius:8px;padding:8px 12px;margin-top:10px;font-size:13px}
.why .whyh{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.why ul{margin:6px 0 4px;padding-left:20px}.why li{margin:2px 0}.evl{margin-top:4px}
.meter{display:inline-block;width:110px;height:8px;background:#e3e8ee;border-radius:4px;overflow:hidden}.meter i{display:block;height:100%}
.meter i.hi{background:#2e7d32}.meter i.mid{background:#f9a825}.meter i.lo{background:#c62828}
.qrow{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0}.qchip,.plat,.batch{white-space:nowrap;font-size:11px;font-weight:700;padding:1px 8px;border-radius:10px;border:1px solid #cfd8dc;background:#eef2f6;color:#37474f;text-decoration:none}
.qchip.ok{background:#e8f5e9;color:#1b5e20;border-color:#a5d6a7}.qchip.warn{background:#fff8e1;color:#8a5a00;border-color:#ffe082}.qchip.bad{background:#fdecea;color:#b71c1c;border-color:#ef9a9a}
.qchip.lv-high{background:#fdecea;color:#b71c1c;border-color:#ef9a9a}.qchip.lv-medium{background:#fff3e0;color:#8a4b00;border-color:#ffcc80}.qchip.lv-low{background:#e8f5e9;color:#1b5e20;border-color:#a5d6a7}
.plat{background:#e0f2f1;color:#00695c;border-color:#80cbc4}.batch{background:#ede7f6;color:#4527a0;border-color:#b39ddb}
.score{position:relative;height:16px;background:#eef2f6;border-radius:8px;overflow:hidden}.score i{display:block;height:100%}.score span{position:absolute;left:8px;top:0;font-size:11px;font-weight:700;line-height:16px}
.score.lv-high i{background:#ef9a9a}.score.lv-medium i{background:#ffcc80}.score.lv-low i{background:#a5d6a7}tr.hot td{background:#fff8f6}
a.iid{color:inherit;text-decoration:none}a.iid:hover::after{content:" 🔗";font-size:12px}
.card.kfocus{outline:3px solid #7e57c2;outline-offset:2px}.card.flashc{animation:flashc 1.6s}@keyframes flashc{0%{box-shadow:0 0 0 6px #ffe082}100%{box-shadow:none}}
.hl-k{color:#a626a4;font-weight:600}.hl-s{color:#50a14f}.hl-c{color:#8e99a6;font-style:italic}.hl-n{color:#986801}.hl-t{color:#0b6bcb}.hl-a{color:#c18401}.hl-d{color:#e45649;font-weight:600}
table.list td{overflow-wrap:anywhere}.card,tr.ev,h2,#areas,#repo-risks{scroll-margin-top:calc(var(--bar,60px) + 10px)}
/* ---- areas overview */
#areas{margin-top:14px}#areas table td{vertical-align:middle}#areas a.t{font:11px SFMono-Regular,Menlo,monospace;padding:1px 6px;margin:1px;border-radius:6px;text-decoration:none;border:1px solid #cfd8dc;display:inline-block}
#areas a.t.pend{background:#fff8e1;color:#8a5a00;border-color:#ffe082}#areas a.t.done{background:#e8f5e9;color:#1b5e20;border-color:#a5d6a7}#areas a.t.conf{background:#fdecea;color:#b71c1c}
#areas a.an{cursor:pointer;font-weight:700}
/* ---- progress bar + minimap + help */
#pbar{position:absolute;left:0;right:0;bottom:-1px;height:3px;background:transparent}#pbar i{display:block;height:100%;width:0;background:#2e7d32;transition:width .3s}
#minimap{position:fixed;right:6px;top:70px;bottom:20px;width:14px;z-index:6;display:flex;flex-direction:column;gap:2px;justify-content:center}
#minimap a{display:block;flex:0 1 14px;min-height:3px;border-radius:3px;background:#ffcc80;opacity:.85}#minimap a.done{background:#81c784}#minimap a.conf{background:#e57373}
#minimap a.need{box-shadow:inset 0 0 0 2px #b71c1c}#minimap a.hid{opacity:.15}#minimap a.cur{outline:2px solid #7e57c2}#minimap a:hover{opacity:1;transform:scaleX(1.4)}
#khelp{position:fixed;right:30px;bottom:30px;z-index:30;background:#fff;border:1px solid #cfd8dc;border-radius:10px;padding:12px 16px;box-shadow:0 8px 30px #0003;font-size:13px}
#khelp td{padding:2px 8px}kbd{font:11px SFMono-Regular,Menlo,monospace;background:#eef2f6;border:1px solid #cfd8dc;border-bottom-width:2px;border-radius:4px;padding:0 5px}
@media (max-width:900px){#minimap{display:none}}
/* ---- dark theme (auto via prefers-color-scheme, or forced with the ◐ button / d key) */
html[data-theme=dark]{color-scheme:dark}
html[data-theme=dark] body{background:#0f141a;color:#d7dee6}
html[data-theme=dark] .card,html[data-theme=dark] .tile,html[data-theme=dark] .meta,html[data-theme=dark] details,html[data-theme=dark] #tracker,
html[data-theme=dark] #repo-risks,html[data-theme=dark] table.list,html[data-theme=dark] #khelp,html[data-theme=dark] dialog#pdlg{background:#161d25;border-color:#2a3440;color:#d7dee6}
html[data-theme=dark] h2{border-color:#2a3440}html[data-theme=dark] h5,html[data-theme=dark] .meta b,html[data-theme=dark] .muted{color:#8b98a7}
html[data-theme=dark] .bar{background:#11171ee6;border-color:#2a3440}html[data-theme=dark] .bar input,html[data-theme=dark] .bar select,html[data-theme=dark] textarea{background:#0f141a;color:#d7dee6;border-color:#2a3440}
html[data-theme=dark] table.list th,html[data-theme=dark] table.pairs th,html[data-theme=dark] table.devt th{background:#1d2630}
html[data-theme=dark] table.list td,html[data-theme=dark] table.list th,html[data-theme=dark] table.pairs td{border-color:#2a3440}
html[data-theme=dark] table.code{background:#0d1217;border-color:#2a3440}html[data-theme=dark] td.ln,html[data-theme=dark] td.who{border-color:#2a3440}html[data-theme=dark] td.who{color:#b39ddb}
html[data-theme=dark] tr.add td.lc{background:#12301c}html[data-theme=dark] tr.del td.lc{background:#3a1717}html[data-theme=dark] tr.chg td.lc{background:#3a2c10}
html[data-theme=dark] tr.ev td.lc{background:#2a2148!important}html[data-theme=dark] .code.empty{border-color:#2a3440}
html[data-theme=dark] code,html[data-theme=dark] .path code,html[data-theme=dark] .mapping code,html[data-theme=dark] .dev code,html[data-theme=dark] .dep,html[data-theme=dark] kbd{background:#1d2630;color:#d7dee6;border-color:#2a3440}
html[data-theme=dark] .ai,html[data-theme=dark] .why{background:#1c1830;border-color:#3b3263}html[data-theme=dark] .ai.pending{background:#2b2510;border-color:#5c4b14}
html[data-theme=dark] .esc,html[data-theme=dark] .ready.bad,html[data-theme=dark] .revs.conf{background:#2d1616;border-color:#5c2a2a}
html[data-theme=dark] .aidec,html[data-theme=dark] .ready.ok{background:#132718;border-color:#2c5434}
html[data-theme=dark] .decision,html[data-theme=dark] .revs{background:#121920;border-color:#2a3440}html[data-theme=dark] .opt{background:#161d25;border-color:#2a3440}
html[data-theme=dark] .cp{background:#10243a;border-color:#1f4a75}html[data-theme=dark] .card.is-done{background:#131c16}html[data-theme=dark] .card.is-conf{background:#221414}
html[data-theme=dark] .mapping{color:#aab6c3}html[data-theme=dark] .signals{color:#f0b46a}html[data-theme=dark] tr.hot td{background:#261a17}
html[data-theme=dark] .hl-k{color:#c678dd}html[data-theme=dark] .hl-s{color:#98c379}html[data-theme=dark] .hl-c{color:#6b7785}html[data-theme=dark] .hl-n{color:#d19a66}
html[data-theme=dark] .hl-t{color:#61afef}html[data-theme=dark] .hl-a{color:#e5c07b}html[data-theme=dark] .hl-d{color:#ef6b73}
html[data-theme=dark] a{color:#7cb7ff}html[data-theme=dark] .chip{background:#1d2630;color:#d7dee6}
html[data-theme=dark] .chip.ok,html[data-theme=dark] .rs.done{background:#132718;color:#9be0a5;border-color:#2c5434}html[data-theme=dark] .chip.bad,html[data-theme=dark] .rs.conf{background:#2d1616;color:#ff9e9e;border-color:#5c2a2a}
html[data-theme=dark] .rs.pend{background:#2b2510;color:#ffcf70;border-color:#5c4b14}html[data-theme=dark] .score{background:#1d2630}
/* ---- print / PDF */
@page{margin:12mm}
@media print{#minimap,#khelp,#pbar,.c-res,.why .evl,#areas a.an::after{display:none!important}
 body{background:#fff!important;color:#000!important;font-size:11px}.wrap{max-width:none;padding:0}
 .cols.cols4{grid-template-columns:repeat(3,minmax(0,1fr))}table.code{font-size:9px;overflow:visible}table.code td{white-space:pre-wrap;word-break:break-all}
 .opt:not(:has(input:checked)){display:none}.opt{border:0;padding:0}.opt input{display:none}.decision{border:0;padding:0;background:none}
 .decision textarea{border:0;min-height:0;resize:none}.decision textarea:placeholder-shown{display:none}
 h2{break-before:page;break-after:avoid}h2#decide,h2#quality{break-before:auto}.card,.why,tr{break-inside:avoid}
 details>summary{list-style:none}a{color:inherit;text-decoration:none}.card.kfocus{outline:0}
 .wrap::before{content:attr(data-print);display:block;font-size:10px;color:#555;margin-bottom:6px}}
"""

EXTRA3_CSS = r"""
/* ---- v3 */
.qchip.hist{background:#fbe9e7;color:#bf360c;border-color:#ffab91}.qchip.new{background:#e3f2fd;color:#0d47a1;border-color:#90caf9}
.card.unseen{box-shadow:inset 4px 0 0 #1e88e5}
button.asg{font-size:11px;font-weight:700;border:1px dashed #90a4ae;background:transparent;color:#546e7a;border-radius:10px;padding:1px 8px;cursor:pointer;margin-left:auto}
button.asg.on{border-style:solid;background:#e8eaf6;color:#283593;border-color:#9fa8da}.card header .rs{margin-left:6px}
.qa{background:#f1f8e9;border:1px solid #c5e1a5;border-radius:8px;padding:6px 12px;margin-top:10px;font-size:13px}.qa ul{margin:4px 0;padding-left:4px;list-style:none}.qa li{margin:2px 0}
.qa input:checked+span{text-decoration:line-through;color:#78909c}
details.calls{margin-top:8px;font-size:13px}details.calls table{font-size:12px}
#seenbar{background:#e3f2fd;border:1px solid #90caf9;border-radius:8px;padding:8px 12px;margin-top:12px}#seenbar button{margin-left:8px}
#q{width:190px}#qcount{font-size:12px;font-weight:700;color:#1565c0}
ul.qal{padding-left:18px}ul.qal ul{padding-left:18px;list-style:none}li.qd{color:#78909c;text-decoration:line-through}
pre#commitprev{background:#0f1720;color:#e6edf3;padding:10px 12px;border-radius:8px;overflow:auto;font:12px/1.5 SFMono-Regular,Menlo,Consolas,monospace;max-height:420px;white-space:pre-wrap}
.inl{display:none;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:10px;margin-top:6px}.inl>div{min-width:0}body.diff-inline .inl{display:grid}
body.diff-inline .cols.cols4{grid-template-columns:1fr}body.diff-inline .cols>div:not(.c-res){display:none}
body.nobase:not(.diff-inline) .c-base{display:none}body.nobase:not(.diff-inline) .cols.cols4{grid-template-columns:repeat(3,minmax(0,1fr))}
table.udiff td.sg{color:#90a4ae;width:12px;user-select:none}table.udiff tr.add td.lc{background:#e6f4ea}table.udiff tr.del td.lc{background:#fdecea}
@media (max-width:1000px){.inl{grid-template-columns:1fr}}
html[data-theme=dark] .qa{background:#15210f;border-color:#2f4a1e}html[data-theme=dark] #seenbar{background:#10243a;border-color:#1f4a75}
html[data-theme=dark] .qchip.new{background:#10243a;color:#90caf9;border-color:#1f4a75}html[data-theme=dark] .qchip.hist{background:#2d1a12;color:#ffab91;border-color:#5c3424}
html[data-theme=dark] button.asg.on{background:#1a1f3a;color:#9fa8da}html[data-theme=dark] table.udiff tr.add td.lc{background:#12301c}html[data-theme=dark] table.udiff tr.del td.lc{background:#3a1717}
@media print{button.asg,#seenbar,details.calls,.seenchip,#q,#qcount{display:none!important}.qa input{display:inline}}
"""

EXTRA3_JS = r"""
/* ===== v3: search · assign · seen-since-last-open · behaviour checklist · QA plan · commit preview · inline diff ===== */
const LS={get(k,d){try{const v=localStorage.getItem(k);return v==null?d:JSON.parse(v);}catch(e){return d;}},set(k,v){try{localStorage.setItem(k,JSON.stringify(v));}catch(e){}}};
const SKEY=KEY+'-seen',QKEY=KEY+'-qa',GKEY=KEY+'-assign',VKEY='merge-report-view';
let QA=LS.get(QKEY,{}),ASSIGN=LS.get(GKEY,{}),SEARCH='',ONLYNEW=false;
const ALLCARDS=[...document.querySelectorAll('.card')];
ALLCARDS.forEach(c=>{c._txt=null;});
const txtOf=c=>c._txt||(c._txt=c.textContent.toLowerCase());
const me=()=>(document.getElementById('by').value||'').trim();
function assigneeOf(id){if(ASSIGN[id])return ASSIGN[id];for(const[w,f]of Object.entries(IMPORTS))if(f.assignments&&f.assignments[id])return f.assignments[id];return '';}
function extraMatch(card){const id=card.id;
 if(SEARCH&&!SEARCH.split(/\s+/).every(w=>txtOf(card).includes(w)))return false;
 const a=(document.getElementById('rassign')||{}).value;const who=assigneeOf(id);
 if(a==='me'&&(!me()||who!==me()))return false;if(a==='none'&&who)return false;if(a==='any'&&!who)return false;
 if(ONLYNEW&&!card.classList.contains('unseen'))return false;return true;}
const _matchDev3=matchDev;matchDev=function(c){return _matchDev3(c)&&extraMatch(c.card);};
function filterLoose(){/* cards without decision controls (auto-applied) follow search / only-new too */
 const active=SEARCH||ONLYNEW;ALLCARDS.forEach(c=>{if(c.querySelector('.decision'))return;c.style.display=(!active||extraMatch(c))?'':'none';
  if(active&&extraMatch(c)){const d=c.closest('details');if(d)d.open=true;}});
 if(active)document.querySelectorAll('details:not(.hist):not(.calls)').forEach(d=>{if(d.querySelector('.card'))d.open=true;});
 const n=ALLCARDS.filter(c=>c.style.display!=='none'&&(!c.querySelector('.decision')||matchDev(BYID[c.id]||{card:c,devs:[]}))).length;
 const qc=document.getElementById('qcount');if(qc)qc.textContent=active?n+' match':'';}

/* search box: "/" focuses */
const qin=document.getElementById('q');let qT=null;
if(qin)qin.addEventListener('input',()=>{clearTimeout(qT);qT=setTimeout(()=>{SEARCH=qin.value.trim().toLowerCase();refresh();},150);});

/* assign me */
function saveAssign(){LS.set(GKEY,ASSIGN);if(typeof touched==='function')touched();}
function paintAssign(){CARDS.forEach(c=>{let b=c.card.querySelector('.asg');if(!b){b=document.createElement('button');b.className='asg';b.type='button';c.card.querySelector('header').insertBefore(b,c.badge);}
 const w=assigneeOf(c.id);b.textContent=w?'👤 '+w:'＋ Assign me';b.classList.toggle('on',!!w);b.title=w?(ASSIGN[c.id]?'Assigned here — click to unassign':'Assigned in an imported file'):'Assign this card to the name in “Decided by”';});}
function toggleAssign(id){if(ASSIGN[id]){delete ASSIGN[id];}else{let n=me();if(!n){n=(prompt('Your name (also fills “Decided by”):')||'').trim();if(!n)return;document.getElementById('by').value=n;save();}ASSIGN[id]=n;}
 saveAssign();refresh();}
document.addEventListener('click',e=>{const b=e.target.closest('button.asg');if(b){e.preventDefault();toggleAssign(b.closest('.card').id);}});
const ra=document.getElementById('rassign');if(ra)ra.addEventListener('change',refresh);

/* changed since you last opened (per browser) */
function paintSeen(){const seen=LS.get(SKEY,null);const first=!seen;const s=seen||{};let n=0;
 ALLCARDS.forEach(c=>{const fp=c.dataset.fp;if(!fp)return;const un=!first&&s[c.id]!==fp;c.classList.toggle('unseen',un);
  let chip=c.querySelector('.seenchip');if(un){n++;if(!chip){chip=document.createElement('span');chip.className='qchip new seenchip';chip.title='Different from the last time this report was open in this browser';c.querySelector('header').appendChild(chip);}chip.textContent=s[c.id]?'● changed since you last opened':'● new since you last opened';}
  else if(chip)chip.remove();});
 if(first)markAllSeen(true);
 const bn=document.getElementById('seenbar');if(bn){bn.hidden=!n;bn.querySelector('b').textContent=n+' card'+(n===1?'':'s')+' changed since you last opened this report';}}
function markSeen(card){if(!card||!card.dataset.fp)return;const s=LS.get(SKEY,null);if(!s)return;  /* baseline is set by paintSeen on first open */
 s[card.id]=card.dataset.fp;LS.set(SKEY,s);card.classList.remove('unseen');const ch=card.querySelector('.seenchip');if(ch)ch.remove();
 const bn=document.getElementById('seenbar');const n=document.querySelectorAll('.card.unseen').length;if(bn){bn.hidden=!n;bn.querySelector('b').textContent=n+' card'+(n===1?'':'s')+' changed since you last opened this report';}}
function markAllSeen(silent){const s={};ALLCARDS.forEach(c=>{if(c.dataset.fp)s[c.id]=c.dataset.fp;});LS.set(SKEY,s);
 if(!silent){ALLCARDS.forEach(c=>{c.classList.remove('unseen');const ch=c.querySelector('.seenchip');if(ch)ch.remove();});ONLYNEW=false;document.getElementById('seenbar').hidden=true;refresh();}}
function onlyNew(){ONLYNEW=!ONLYNEW;document.getElementById('onlynew').textContent=ONLYNEW?'Show all cards':'Show only these';refresh();}
const _setFocus3=setFocus;setFocus=function(c,scroll){_setFocus3(c,scroll);if(c)markSeen(c);};
document.addEventListener('change',e=>{const c=e.target.closest('.card');if(c&&e.target.closest('.decision'))markSeen(c);});

/* behaviour checklist */
function saveQA(){LS.set(QKEY,QA);if(typeof touched==='function')touched();}
function applyQA(){document.querySelectorAll('.qak').forEach(x=>{x.checked=!!QA[x.dataset.k];});}
document.addEventListener('change',e=>{if(e.target.classList&&e.target.classList.contains('qak')){if(e.target.checked)QA[e.target.dataset.k]=me()||true;else delete QA[e.target.dataset.k];saveQA();paintQAPlan();}});

/* export / auto-save / import carry assignments and checklist ticks */
const _buildOut3=buildOut;buildOut=function(){const o=_buildOut3();o.assignments=ASSIGN;o.qa=QA;return o;};
const _snap3=snapshot;snapshot=function(){const s=_snap3();s.qa=QA;s.assign=ASSIGN;return s;};
const _restore3=restoreLocal;restoreLocal=function(L){if(L.qa){QA=L.qa;LS.set(QKEY,QA);}if(L.assign){ASSIGN=L.assign;LS.set(GKEY,ASSIGN);}_restore3(L);applyQA();};

/* QA test plan: every checklist, grouped by area */
function qaItems(){return [...document.querySelectorAll('.qa')].map(q=>{const card=q.closest('.card');
 return {id:q.dataset.id,area:card.dataset.area||'',title:(card.querySelector('.ttl')||{}).textContent||'',path:(card.querySelector('.path code')||{}).textContent||'',
  plat:[...card.querySelectorAll('.plat')].map(p=>p.textContent),checks:[...q.querySelectorAll('.qak')].map(x=>({k:x.dataset.k,t:x.parentElement.textContent.trim(),done:!!QA[x.dataset.k]}))};});}
function qaMarkdown(){const by={};qaItems().forEach(x=>(by[x.area]=by[x.area]||[]).push(x));
 let t=`# QA test plan — ${RID}\n\nGenerated from the merge report (${new Date().toLocaleString()}). Tick each check on a real device.\n`;
 Object.keys(by).sort().forEach(a=>{t+=`\n## ${a}\n`;by[a].forEach(x=>{t+=`\n**${x.id}** — ${x.title}${x.plat.length?' · '+x.plat.join(', '):''}\n\`${x.path}\`\n`;x.checks.forEach(c=>{t+=`- [${c.done?'x':' '}] ${c.t}\n`;});});});return t;}
function paintQAPlan(){const box=document.getElementById('qaplan');if(!box)return;const its=qaItems();const all=its.reduce((a,x)=>a+x.checks.length,0),done=its.reduce((a,x)=>a+x.checks.filter(c=>c.done).length,0);
 const by={};its.forEach(x=>(by[x.area]=by[x.area]||[]).push(x));
 box.innerHTML=`<div class="rmeter"><i style="width:${all?done*100/all:0}%"></i></div><b>${done} / ${all}</b> checks done across ${its.length} cards · `+
  `<button class="cpbtn" type="button" onclick="copyText(qaMarkdown(),'QA test plan')">Copy as Markdown</button><button class="cpbtn alt" type="button" onclick="downloadText(qaMarkdown(),'qa-test-plan-'+RID+'.md')">Download .md</button>`+
  Object.keys(by).sort().map(a=>{const x=by[a];const n=x.reduce((s,y)=>s+y.checks.length,0),d=x.reduce((s,y)=>s+y.checks.filter(c=>c.done).length,0);
   return `<details${d<n?' open':''}><summary>${esc(a)} — ${d}/${n}</summary><ul class="qal">`+x.map(y=>`<li><a class="dep" href="#${y.id}">${y.id}</a> ${esc(y.title)} ${y.plat.map(p=>`<span class="plat">${esc(p)}</span>`).join(' ')}<ul>`+
    y.checks.map(c=>`<li class="${c.done?'qd':''}">${c.done?'☑':'☐'} ${esc(c.t)}</li>`).join('')+'</ul></li>').join('')+'</ul></details>';}).join('');}
function downloadText(t,name){const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([t],{type:'text/markdown'}));a.download=name;a.click();}

/* commit message preview (live; the real file is written by commit_message.py) */
function commitText(){const D=COMMIT_DATA;const groups={},dropped=[],open=[];
 D.rows.forEach(r=>{const c=BYID[r.id];const ch=c?((c.el.querySelector('input[type=radio]:checked')||{}).value||''):r.dec;
  const who=c&&c._st&&(c._st.L.sel)?' (dev)':(r.by==='ai'?' (AI)':ch?' (dev)':'');
  const tag=`${r.id} ${r.cat}`+(ch?` → ${ch}${who}`:'')+(r.sym?` [${r.sym}]`:'');
  const notes=c?c.el.querySelector('textarea').value.trim():'';
  if(ch==='TARGET'){dropped.push(`- ${r.file} -- ${tag} -- by ${r.who.join(', ')}`+(notes?` -- note: ${notes.split('\n')[0]}`:''));return;}
  if(c&&(c.sec==='decide'||c.sec==='recheck')&&!ch)open.push(`- ${r.id} ${r.file}`);
  (groups[r.who[0]]=groups[r.who[0]]||[]).push(`- ${r.file} -- ${tag}`+(notes&&!notes.startsWith('AI (confidence')?` -- ${notes.split('\n')[0]}`:''));});
 let t=`Merge ${D.src} into ${D.tgt}\n\nReport: ${D.rid}\n`;
 Object.keys(groups).forEach(g=>{t+=`\n${g}\n${groups[g].join('\n')}\n`;});
 if(dropped.length)t+=`\nNot merged (target kept on purpose)\n${dropped.join('\n')}\n`;
 if(open.length)t+=`\nSTILL UNDECIDED — do not commit yet\n${open.join('\n')}\n`;
 t+=`\nFull report: ${D.folder}/report.html`;return t;}
function paintCommit(){const p=document.getElementById('commitprev');if(p)p.textContent=commitText();}

/* inline diff (base → source, base → target) and hide-base */
function rowsOf(col){const t=col&&col.querySelector('table.code');if(!t)return [];return [...t.rows].map(r=>({n:r.cells[0].textContent,t:r.cells[2].textContent.replace(/ /g,'')}));}
function lcsDiff(a,b){const n=a.length,m=b.length,L=Array.from({length:n+1},()=>new Int16Array(m+1));
 for(let i=n-1;i>=0;i--)for(let j=m-1;j>=0;j--)L[i][j]=a[i].t===b[j].t?L[i+1][j+1]+1:Math.max(L[i+1][j],L[i][j+1]);
 const out=[];let i=0,j=0;while(i<n&&j<m){if(a[i].t===b[j].t){out.push([' ',b[j]]);i++;j++;}else if(L[i+1][j]>=L[i][j+1])out.push(['-',a[i++]]);else out.push(['+',b[j++]]);}
 while(i<n)out.push(['-',a[i++]]);while(j<m)out.push(['+',b[j++]]);return out;}
function inlineTable(base,other,label){if(!other.length)return `<h5>${label}</h5><div class="code empty">— not present —</div>`;
 const d=lcsDiff(base,other);return `<h5>${label}</h5><table class="code udiff">`+d.map(([k,r])=>`<tr class="${k==='+'?'add':k==='-'?'del':''}"><td class="ln">${k==='-'?r.n:''}</td><td class="ln">${k!=='-'?r.n:''}</td><td class="sg">${k}</td><td class="lc">${esc(r.t)||'&nbsp;'}</td></tr>`).join('')+'</table>';}
function buildInline(card){const cols=card.querySelector('.cols');if(!cols||card.querySelector('.inl'))return;
 const b=rowsOf(cols.querySelector('.c-base')),s=rowsOf(cols.querySelector('.c-src')),t=rowsOf(cols.querySelector('.c-tgt'));
 const div=document.createElement('div');div.className='inl';div.innerHTML=`<div>${inlineTable(b,s,'Base → Source (incoming)')}</div><div>${inlineTable(b,t,'Base → Target (current)')}</div>`;
 cols.parentNode.insertBefore(div,cols);highlightAll(div);}
function applyView(){const v=LS.get(VKEY,{});document.body.classList.toggle('diff-inline',!!v.inline);document.body.classList.toggle('nobase',!!v.nobase);
 if(v.inline)ALLCARDS.forEach(buildInline);const a=document.getElementById('vdiff'),b=document.getElementById('vbase');
 if(a)a.textContent=v.inline?'Diff: inline':'Diff: 3-way';if(b){b.textContent=v.nobase?'Base: hidden':'Base: shown';b.disabled=!!v.inline;}}
function toggleView(k){const v=LS.get(VKEY,{});v[k]=!v[k];LS.set(VKEY,v);applyView();}

/* keys: / search · i inline diff · m assign me */
document.addEventListener('keydown',e=>{const tg=e.target;if(e.metaKey||e.ctrlKey||e.altKey||tg.matches('textarea,input:not([type=radio]):not([type=checkbox]),select'))return;
 if(e.key==='/'){e.preventDefault();e.stopImmediatePropagation();qin&&qin.focus();qin&&qin.select();}
 else if(e.key==='i'){e.stopImmediatePropagation();toggleView('inline');}
 else if(e.key==='m'&&CUR){e.stopImmediatePropagation();toggleAssign(CUR.id);}},true);

const _refresh3=refresh;refresh=function(){_refresh3();filterLoose();paintAssign();paintQAPlan();paintCommit();paintMinimap();};
document.addEventListener('input',e=>{if(e.target.tagName==='TEXTAREA')paintCommit();});
window.addEventListener('load',()=>{applyQA();applyView();paintSeen();refresh();});
"""

EXTRA4_CSS = r"""
/* ===== v4: friendlier UI ===== */
/* top bar + menus */
.bar{display:block;padding:6px 16px;z-index:20}.brow{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.grow{flex:1 1 10px}
.bar .rid{font-weight:800;color:inherit;text-decoration:none;flex:0 1 auto;min-width:60px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.brow>*:not(.rid):not(.grow){flex:none}.bar #q{width:170px}.bar #by{width:110px}
@media (min-width:1100px){.brow{flex-wrap:nowrap}}
details.menu{position:relative;background:none;border:0;padding:0;margin:0;border-radius:0}
details.menu>summary{list-style:none}details.menu>summary::-webkit-details-marker{display:none}
summary.btn{background:#546e7a;color:#fff;border-radius:6px;padding:7px 12px;font-weight:600;cursor:pointer;user-select:none;white-space:nowrap}
#fmenu.active>summary{background:#1565c0}
.pop{position:absolute;top:calc(100% + 6px);left:0;z-index:40;background:#fff;border:1px solid #dde3ea;border-radius:10px;box-shadow:0 10px 30px #0002;padding:12px;display:flex;flex-direction:column;gap:8px;min-width:250px;max-height:75vh;overflow:auto}
.menu.right .pop{left:auto;right:0}.pop label{display:flex;flex-direction:column;gap:2px;font-size:12px;font-weight:600;color:#5b6775}.pop select{max-width:none;width:100%}
.pop button{text-align:left}.ph{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#5b6775;font-weight:700;margin-top:6px;border-top:1px solid #eef2f6;padding-top:8px}
.ph:first-child{margin-top:0;border-top:0;padding-top:0}.jl a{display:inline-block;margin:2px 8px 2px 0;font-size:13px}
/* side table of contents (wide screens; otherwise ⋯ → Jump to) */
#toc{display:none}
@media (min-width:1560px){body{padding-left:180px}#toc{display:block;position:fixed;left:12px;top:calc(var(--bar,60px) + 18px);width:160px;font-size:13px;z-index:4}
 #toc a{display:block;padding:4px 8px;border-radius:6px;color:#37474f;text-decoration:none;border-left:3px solid transparent}
 #toc a.on{background:#eef2f6;font-weight:700;border-left-color:#546e7a}#toc a:hover{background:#f4f6f8}}
/* start here */
#start{background:#fff;border:1px solid #dde3ea;border-left:6px solid #90a4ae;border-radius:12px;padding:14px 18px;margin:14px 0 10px}
#start.s-block{border-left-color:#c62828}#start.s-look{border-left-color:#f9a825}#start.s-ok{border-left-color:#2e7d32}
#start .sh{font-size:20px;font-weight:800}#start ul{list-style:none;padding:0;margin:8px 0}#start li{margin:4px 0;display:flex;gap:8px;align-items:baseline}
#start li .ic{width:18px;text-align:center;flex:none}#start li.block .ic{color:#c62828}#start li.look .ic{color:#e69500}#start li.ok .ic{color:#2e7d32}#start li.info .ic{color:#78909c}
#startnext{margin-top:10px;padding:10px 12px;background:#f4f6f8;border-radius:8px;font-size:15px}#startnext a.go{margin-left:8px;background:#1565c0;color:#fff;border-radius:6px;padding:3px 12px;text-decoration:none;font-weight:700;font-size:13px}
details.aux{margin:8px 0}details.aux>summary{color:#37474f}
/* collapsed cards */
.verdict{margin:6px 0 2px;font-size:14px}.verdict .muted{font-size:12.5px;margin-top:1px}.v-look{color:#8a5a00}
.spath code{font:12px SFMono-Regular,Menlo,monospace;color:#5b6775;word-break:break-all}
button.more-t{background:none;border:0;color:#1565c0;font-weight:600;cursor:pointer;padding:6px 0 0;font-size:13px}
.card:not(.open) .more{display:none}.card .more{border-top:1px dashed #dde3ea;margin-top:8px;padding-top:6px}
.cols.cols3{grid-template-columns:repeat(3,minmax(0,1fr))}@media (max-width:1000px){.cols.cols3{grid-template-columns:1fr}}
.qrow .chipmore{font-size:11px;font-weight:700;padding:1px 8px;border-radius:10px;border:1px dashed #b0bec5;background:none;color:#546e7a;cursor:pointer}
/* ? tooltips */
.tip{display:inline-flex;align-items:center;justify-content:center;width:15px;height:15px;border-radius:50%;background:#cfd8dc;color:#37474f;font:700 10px/1 -apple-system,sans-serif;
 cursor:help;position:relative;vertical-align:1px;text-transform:none;letter-spacing:0;margin-left:2px}
.tip:hover::after,.tip:focus::after{content:attr(data-tip);position:absolute;left:50%;top:140%;transform:translateX(-50%);width:270px;background:#263238;color:#fff;padding:8px 10px;
 border-radius:8px;font:400 12px/1.45 -apple-system,BlinkMacSystemFont,sans-serif;z-index:60;white-space:normal;text-align:left;text-transform:none;letter-spacing:0;box-shadow:0 6px 20px #0004}
/* ===== one meaning per colour: red = blocks the merge · amber = needs a look · green = done / fine · grey = information ===== */
.badge{font-weight:700;border:1px solid transparent}.badge.b-look{background:#fff3e0;color:#8a4b00;border-color:#ffcc80}.badge.b-info{background:#eef2f6;color:#455a64;border-color:#cfd8dc}
.sev{color:#78909c}.sev.sev-high{color:#37474f}
.qchip,.plat,.batch,.qchip.hist,.qchip.lv-medium,.qchip.lv-low{background:#eef2f6;color:#455a64;border-color:#cfd8dc}
.qchip.look,.qchip.warn,.qchip.bad,.qchip.lv-high,.qchip.new{background:#fff3e0;color:#8a4b00;border-color:#ffcc80}
.qchip.ok{background:#e8f5e9;color:#1b5e20;border-color:#a5d6a7}.qchip.block{background:#fdecea;color:#b71c1c;border-color:#ef9a9a}
.risk,.risk.r-drops,.risk.r-doubt,.risk.r-reverted,.risk.r-lookalike{background:#fff3e0;color:#8a4b00;border-color:#ffcc80}
.risk.r-recheck,.risk.r-secret{background:#fdecea;color:#b71c1c;border-color:#ef9a9a}
.card,.card.sev-high,.card.sev-medium,.card.sev-low{border-left-color:#cfd8dc}.need .card{border-left-color:#f9a825}.card.blocking{border-left-color:#c62828}
.card.is-done{border-left-color:#2e7d32!important}.card.unseen{box-shadow:inset 4px 0 0 #f9a825}
.ai,.why{background:#f6f8fa;border-color:#dde3ea}.why{border-left-color:#90a4ae}.qa{background:#f6f8fa;border-color:#dde3ea}
.cp{background:#fff8e1;border-color:#ffe082}#seenbar{background:#fff8e1;border-color:#ffe082}
html[data-theme=dark] .pop{background:#161d25;border-color:#2a3440}html[data-theme=dark] .ph{border-color:#2a3440;color:#8b98a7}html[data-theme=dark] .pop label{color:#8b98a7}
html[data-theme=dark] #start{background:#161d25;border-color:#2a3440}html[data-theme=dark] #startnext{background:#1d2630}html[data-theme=dark] details.aux>summary{color:#d7dee6}
html[data-theme=dark] #toc a{color:#aab6c3}html[data-theme=dark] #toc a.on,html[data-theme=dark] #toc a:hover{background:#1d2630}
html[data-theme=dark] .spath code{color:#8b98a7;background:none}html[data-theme=dark] .card .more{border-color:#2a3440}html[data-theme=dark] .tip{background:#2a3440;color:#d7dee6}
html[data-theme=dark] .badge.b-look,html[data-theme=dark] .qchip.look,html[data-theme=dark] .qchip.warn,html[data-theme=dark] .qchip.bad,html[data-theme=dark] .qchip.lv-high,html[data-theme=dark] .qchip.new,
html[data-theme=dark] .risk,html[data-theme=dark] .cp,html[data-theme=dark] #seenbar{background:#2b2510;color:#ffcf70;border-color:#5c4b14}
html[data-theme=dark] .badge.b-info,html[data-theme=dark] .qchip,html[data-theme=dark] .plat,html[data-theme=dark] .batch,html[data-theme=dark] .qchip.hist,html[data-theme=dark] .qchip.lv-medium,html[data-theme=dark] .qchip.lv-low{background:#1d2630;color:#aab6c3;border-color:#2a3440}
html[data-theme=dark] .qchip.ok{background:#132718;color:#9be0a5;border-color:#2c5434}html[data-theme=dark] .qchip.block,html[data-theme=dark] .risk.r-recheck,html[data-theme=dark] .risk.r-secret{background:#2d1616;color:#ff9e9e;border-color:#5c2a2a}
html[data-theme=dark] .ai,html[data-theme=dark] .why,html[data-theme=dark] .qa{background:#121920;border-color:#2a3440}html[data-theme=dark] .v-look{color:#ffcf70}
@media print{#toc,.bar,details.menu,button.more-t,.qrow .chipmore{display:none!important}body{padding-left:0!important}.card .more{display:block!important}.qrow>*{display:inline-block!important}
 details.aux{display:none}#start{break-inside:avoid}}
"""

EXTRA4_JS = r"""
/* ===== v4: menus · filters badge · table of contents · start here · collapsible cards · chip folding ===== */
document.addEventListener('click',e=>{document.querySelectorAll('details.menu[open]').forEach(m=>{if(!m.contains(e.target))m.open=false;});
 const jl=e.target.closest('#mmenu .jl a');if(jl)document.getElementById('mmenu').open=false;});
document.addEventListener('keydown',e=>{if(e.key==='Escape')document.querySelectorAll('details.menu[open]').forEach(m=>m.open=false);});
const FIDS=[['rfilter','all'],['rdev',''],['rrisk',''],['rarea',''],['rassign','']];
function clearFilters(){FIDS.forEach(([id,v])=>{const el=document.getElementById(id);if(el)el.value=v;});const q=document.getElementById('q');if(q){q.value='';SEARCH='';}ONLYNEW=false;refresh();}
function paintFilters(){const n=FIDS.filter(([id,v])=>{const el=document.getElementById(id);return el&&el.value!==v;}).length;
 document.getElementById('fcount').textContent=n?` (${n})`:'';document.getElementById('fmenu').classList.toggle('active',!!n);}

/* table of contents (left on wide screens, ⋯ → Jump to otherwise) */
const TOCNAMES={start:'Start here',recheck:'AI re-check',decide:'Needs you',aidecided:'Decided by AI',devdecided:'Decided by developer',review:'Review',tracker:'Tracker',
 quality:'Quality & risk',history:'History',areas:'Feature areas',qa:'QA test plan',commit:'Commit message',auto:'Auto-applied',paths:'Path map',commits:'Commits'};
function buildToc(){const ids=['start',...[...document.querySelectorAll('.wrap h2[id], #tracker, #areas')].map(h=>h.id)].filter((x,i,a)=>x&&TOCNAMES[x]&&a.indexOf(x)===i);
 const count=id=>{const h=document.getElementById(id);const m=h&&h.tagName==='H2'&&h.firstChild&&String(h.firstChild.textContent).match(/\((\d+)\)/);return m?` <span class="muted">${m[1]}</span>`:'';};
 const links=ids.map(id=>`<a href="#${id}" data-sec="${id}">${TOCNAMES[id]}${count(id)}</a>`).join('')+'<a href="../index.html">All reports ↗</a>';
 document.getElementById('toc').innerHTML=links;document.getElementById('jumplinks').innerHTML=links;
 if('IntersectionObserver' in window){const io=new IntersectionObserver(es=>{es.forEach(en=>{if(en.isIntersecting){document.querySelectorAll('#toc a').forEach(a=>a.classList.toggle('on',a.dataset.sec===en.target.id));}});},{rootMargin:'-20% 0px -70% 0px'});
  ids.forEach(id=>{const el=document.getElementById(id);if(el)io.observe(el);});}}
document.addEventListener('click',e=>{const a=e.target.closest('#toc a[data-sec], .jl a[data-sec]');if(!a)return;const el=document.getElementById(a.dataset.sec);if(!el)return;e.preventDefault();
 for(let n=el.nextElementSibling;n&&n.tagName!=='H2';n=n.nextElementSibling)if(n.tagName==='DETAILS'&&!n.classList.contains('aux'))n.open=true;
 el.scrollIntoView({behavior:'smooth',block:'start'});history.replaceState(null,'','#'+a.dataset.sec);});

/* collapsible cards */
function toggleCard(c,force){if(!c)return;const o=force===undefined?!c.classList.contains('open'):force;c.classList.toggle('open',o);
 const b=c.querySelector('.more-t');if(b){b.textContent=o?'Hide details ▴':'Show details ▾';b.setAttribute('aria-expanded',String(o));}}
function expandAll(v){ALLCARDS.forEach(c=>toggleCard(c,v));document.getElementById('mmenu').open=false;}
document.addEventListener('click',e=>{const b=e.target.closest('button.more-t');if(b){e.preventDefault();toggleCard(b.closest('.card'));}});
const _setFocus4=setFocus;setFocus=function(c,scroll){if(c)toggleCard(c,true);_setFocus4(c,scroll);};
document.addEventListener('keydown',e=>{if(e.key!=='o'||e.metaKey||e.ctrlKey||e.altKey||e.target.matches('textarea,input:not([type=radio]):not([type=checkbox]),select'))return;
 if(CUR){e.stopImmediatePropagation();toggleCard(CUR);}},true);

/* chip rows: show 3, fold the rest behind “+N” */
function foldChips(){document.querySelectorAll('.qrow').forEach(r=>{if(r.dataset.folded)return;r.dataset.folded=1;const k=[...r.children];if(k.length<=3)return;
 k.slice(3).forEach(x=>x.hidden=true);const b=document.createElement('button');b.type='button';b.className='chipmore';b.textContent='+'+(k.length-3);b.title='Show all chips';
 b.onclick=()=>{k.forEach(x=>x.hidden=false);b.remove();};r.appendChild(b);});}

/* start here: one honest status and the next thing to do */
function paintStart(){const box=document.getElementById('start');if(!box||typeof CARDS==='undefined')return;const R=readiness(),D=START_DATA||{};const facts=[];
 const need=CARDS.filter(c=>c.sec==='decide'||c.sec==='recheck');const made=need.filter(c=>{const st=c._st||stateOf(c);return st.L.choice||st.agreed;}).length;
 const tot=CARDS.length,dn=CARDS.filter(c=>(c._st||stateOf(c)).done).length;
 const F=(k,t)=>facts.push([k,t]);
 if(R.ok)F('ok',need.length?`All ${need.length} decisions that need a person are made`:'No decision needs a person — the AI decided every item from the code');
 else F('block',`${R.block.length} thing${R.block.length>1?'s':''} block the merge (see Tracker)`);
 F(dn===tot?'ok':'look',`${dn} of ${tot} decision cards reviewed by a person`);
 if(D.build)F(D.build.ok?'ok':'block',D.build.ok?`Build: all ${D.build.n} schemes succeeded`:`Build: ${D.build.passed}/${D.build.n} schemes succeeded — failing: ${D.build.failed.join(', ')}`+(D.unresolved&&D.unresolved.length?` (unresolved modules: ${D.unresolved.join(', ')})`:''));
 else F('info','Build: not run yet');
 if(D.verify){if(D.missing.length)F('block',`Verification: ${D.missing.length} item${D.missing.length>1?'s':''} lost incoming lines after the merge (${D.missing.join(', ')})`);
  else if(D.rewritten.length)F('look',`Verification: passed, ${D.rewritten.length} rewritten item${D.rewritten.length>1?'s':''} to confirm (${D.rewritten.join(', ')})`);
  else F('ok','Verification: no incoming code lost');}
 else F('info','Verification: not run yet (runs after the merge)');
 if(D.lint&&D.lint.merged)F('look',`${D.lint.merged} new SwiftLint warning${D.lint.merged>1?'s':''} on merged lines`);
 if(D.risk_high)F('look',`${D.risk_high} high-risk file${D.risk_high>1?'s':''} in this merge`);
 const un=document.querySelectorAll('.card.unseen').length;if(un)F('look',`${un} card${un>1?'s':''} changed since you last opened this report`);
 const lvl=facts.some(f=>f[0]==='block')?'block':facts.some(f=>f[0]==='look')?'look':'ok';
 box.className='s-'+lvl;
 document.getElementById('starthead').textContent=lvl==='block'?(R.ok?'Not ready to merge yet — the decisions are done, but other checks fail':'Not ready to merge yet'):lvl==='look'?'Ready to merge, with a few things to check':'Ready to merge ✓';
 const IC={block:'✗',look:'!',ok:'✓',info:'·'};
 document.getElementById('startfacts').innerHTML=facts.map(([k,t])=>`<li class="${k}"><span class="ic">${IC[k]}</span><span>${esc(t)}</span></li>`).join('');
 /* next step */
 let html='',go='';const firstId=t=>{const m=String(t).match(/href="#([^"]+)"/);return m?m[1]:'';};
 const pend=CARDS.filter(c=>{const st=c._st||stateOf(c);return !st.done||st.conflict;});
 if(R.block.length){html=R.block[0];go=firstId(R.block[0]);}
 else if(D.missing&&D.missing.length){go=D.missing[0];html=`Check <b>${go}</b>: a line from the incoming change is missing after the merge.`;}
 else if(D.build&&!D.build.ok){html=`Fix the build — <b>${esc(D.build.failed.join(', '))}</b> failed.`+(D.unresolved&&D.unresolved.length?' The logs point at package resolution; see Quality → Dependencies.':'');go=(D.unresolved&&D.unresolved.length)?'quality':'';}
 else if(pend.length){const c=pend[0];go=c.id;html=`Review <b>${c.id}</b> — ${esc(c.title)}`;}
 else if(D.rewritten&&D.rewritten.length){go=D.rewritten[0];html=`Confirm the rewritten lines in <b>${go}</b> still do what the incoming change intended.`;}
 else html='Everything is checked. Export your decisions, then commit with <code>COMMIT_MSG.txt</code>.';
 document.getElementById('startnext').innerHTML=`<b>Your next step:</b> ${html}`+(go?`<a class="go dep" data-jump="1" href="#${esc(go)}">Go →</a>`:'');}

const _refresh4=refresh;refresh=function(){_refresh4();paintFilters();paintStart();};
window.addEventListener('load',()=>{ALLCARDS.forEach(c=>toggleCard(c,c.classList.contains('open')));foldChips();buildToc();barH();paintStart();});
"""

EXTRA5_CSS = r"""
/* ===== v5: ⋯ menu as a real menu; no horizontal page scroll ===== */
.wrap{overflow-x:clip}.card,.cols>div,.more{min-width:0}
.mpop{width:300px;gap:4px;padding:10px}
.mpop .ph{margin-top:8px;padding-top:10px}.mpop .ph:first-child{margin-top:0;padding-top:0}
.mpop .mi{display:flex;align-items:center;gap:10px;width:100%;background:none;color:inherit;border:0;border-radius:6px;padding:7px 8px;font:500 13.5px/1.2 inherit;cursor:pointer;text-align:left}
.mpop .mi:hover,.mpop .mi:focus-visible{background:#eef2f6;outline:none}.mpop .mic{width:18px;text-align:center;color:#78909c;flex:none}
#rsave{display:flex;flex-direction:column;gap:2px}#rsave .chip{background:none;padding:2px 8px;font-size:12px;font-weight:500;color:#5b6775;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#rsave .chip.ok{color:#1b5e20}#rsave button{display:flex;align-items:center;gap:10px;width:100%;background:none;color:inherit;border:0;border-radius:6px;padding:7px 8px;font:500 13.5px/1.2 inherit;cursor:pointer;text-align:left}
#rsave button:hover{background:#eef2f6}#rsave button::before{content:"💾";width:18px;text-align:center;font-size:12px}#rsave a{font-size:12px;padding:0 8px}
.segrow{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:3px 8px;font-size:13px}.segrow>span{color:#37474f}
.seg{display:inline-flex;border:1px solid #cfd8dc;border-radius:7px;overflow:hidden;flex:none}
.seg button{background:#fff;color:#37474f;border:0;border-left:1px solid #cfd8dc;padding:4px 9px;font:600 12px/1.2 inherit;cursor:pointer}.seg button:first-child{border-left:0}
.seg button:hover{background:#f4f6f8}.seg button.on{background:#546e7a;color:#fff}
.mpop .jl{display:grid;grid-template-columns:1fr 1fr;gap:0 6px;padding:0 4px}.mpop .jl a{display:block;margin:0;padding:4px 4px;border-radius:5px;color:#1565c0;text-decoration:none;font-size:12.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mpop .jl a:hover{background:#eef2f6}
@media (min-width:1560px){.mpop .jump{display:none}}
html[data-theme=dark] .mpop .mi:hover,html[data-theme=dark] #rsave button:hover,html[data-theme=dark] .mpop .jl a:hover,html[data-theme=dark] .seg button:hover{background:#1d2630}
html[data-theme=dark] .segrow>span{color:#aab6c3}html[data-theme=dark] .seg{border-color:#2a3440}html[data-theme=dark] .seg button{background:#161d25;color:#d7dee6;border-color:#2a3440}
html[data-theme=dark] .seg button.on{background:#3b4a57;color:#fff}html[data-theme=dark] .mpop .jl a{color:#7cb7ff}html[data-theme=dark] #rsave .chip{color:#8b98a7}
"""

EXTRA5_JS = r"""
/* ===== v5: segmented controls in the ⋯ menu ===== */
function paintSeg(){const v=LS.get(VKEY,{}),th=themePref();
 document.querySelectorAll('.seg[data-k]').forEach(g=>{const cur=g.dataset.k==='diff'?(v.inline?'1':'0'):g.dataset.k==='base'?(v.nobase?'1':'0'):th;
  g.querySelectorAll('button').forEach(b=>{const on=b.dataset.val===cur;b.classList.toggle('on',on);b.setAttribute('aria-pressed',String(on));});
  if(g.dataset.k==='base')g.querySelectorAll('button').forEach(b=>b.disabled=!!v.inline);});}
document.addEventListener('click',e=>{const b=e.target.closest('.seg[data-k] button');if(!b)return;const k=b.closest('.seg').dataset.k,val=b.dataset.val;
 if(k==='theme'){try{localStorage.setItem(TKEY,val);}catch(_){}applyTheme();}
 else{const v=LS.get(VKEY,{});if(k==='diff')v.inline=val==='1';else v.nobase=val==='1';LS.set(VKEY,v);applyView();}
 paintSeg();});
const _applyView5=applyView;applyView=function(){_applyView5();paintSeg();};
const _applyTheme5=applyTheme;applyTheme=function(){_applyTheme5();paintSeg();};
window.addEventListener('load',paintSeg);
"""

EXTRA6_CSS = r"""
/* ===== v6: Ask AI (Cursor agent via report_server.py) ===== */
.ai-on-only{display:none!important}body.ai-on .ai-on-only{display:inline-flex!important}body.ai-on .ai-off-only{display:none!important}
#aibub{position:fixed;right:30px;bottom:24px;z-index:45;display:none;align-items:center;gap:8px;background:#1565c0;color:#fff;border:0;border-radius:28px;
 padding:12px 18px;font:700 14px/1 -apple-system,BlinkMacSystemFont,sans-serif;box-shadow:0 8px 24px #0d47a155;cursor:pointer}
body.ai-on #aibub{display:inline-flex}#aibub:hover{background:#0d47a1}#aibub .k{font:600 11px/1 SFMono-Regular,Menlo,monospace;background:#ffffff33;border-radius:4px;padding:2px 5px}
#aicall{position:fixed;right:30px;bottom:80px;z-index:45;background:#263238;color:#fff;border-radius:10px;padding:10px 12px;width:260px;font-size:13px;box-shadow:0 8px 24px #0004}
#aicall::after{content:"";position:absolute;right:40px;bottom:-6px;border:6px solid transparent;border-top-color:#263238;border-bottom:0}#aicall kbd{color:#263238}#aicall button{margin-top:6px;background:#ffffff22;color:#fff;border:0;border-radius:6px;padding:4px 10px;cursor:pointer;font-weight:600}
#aipanel{position:fixed;right:24px;bottom:24px;z-index:50;width:min(460px,calc(100vw - 32px));height:min(640px,calc(100vh - 100px));display:flex;flex-direction:column;
 background:#fff;border:1px solid #cfd8dc;border-radius:14px;box-shadow:0 18px 50px #0003;overflow:hidden}
#aipanel[hidden]{display:none}
.aph{display:flex;align-items:center;gap:8px;padding:10px 12px;border-bottom:1px solid #e3e8ee;background:#f7f9fb}.aph b{font-size:14px}.aph .grow{flex:1}
.aph select{border:1px solid #cfd8dc;border-radius:6px;padding:3px 6px;font-size:12px;max-width:190px}.aph button{background:none;border:0;font-size:18px;cursor:pointer;color:#546e7a;padding:0 4px}
.apm{flex:1;overflow:auto;padding:12px;display:flex;flex-direction:column;gap:10px;font-size:13.5px;line-height:1.5}
.amsg{max-width:100%;border-radius:10px;padding:8px 11px}.amsg.u{align-self:flex-end;background:#1565c0;color:#fff;max-width:85%;white-space:pre-wrap}
.amsg.a{background:#f4f6f8;border:1px solid #e3e8ee}.amsg.a p{margin:0 0 6px}.amsg.a p:last-child{margin-bottom:0}.amsg.a ul,.amsg.a ol{margin:4px 0 6px;padding-left:20px}
.amsg.a pre{background:#0f1720;color:#e6edf3;padding:8px 10px;border-radius:8px;overflow:auto;font:12px/1.45 SFMono-Regular,Menlo,monospace;margin:6px 0}
.amsg.a code{font:12px SFMono-Regular,Menlo,monospace;background:#e8edf2;border-radius:4px;padding:0 4px}.amsg.a a.cur{font:12px SFMono-Regular,Menlo,monospace;color:#1565c0}
.amsg.err{background:#fdecea;border:1px solid #ef9a9a;color:#b71c1c}.amsg .tools{font-size:11.5px;color:#78909c;margin-bottom:4px}
.amsg .acts{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}.amsg .acts button{background:#fff;border:1px solid #cfd8dc;border-radius:6px;padding:3px 8px;font-size:12px;cursor:pointer;color:#37474f}
.amsg .acts button:hover{background:#eef2f6}.amsg .meta{font-size:11px;color:#90a4ae;margin-top:4px}
.athink{display:inline-flex;gap:3px}.athink i{width:6px;height:6px;border-radius:50%;background:#90a4ae;animation:aib 1s infinite}.athink i:nth-child(2){animation-delay:.15s}.athink i:nth-child(3){animation-delay:.3s}
@keyframes aib{0%,80%,100%{opacity:.25}40%{opacity:1}}
#aipanel.busy .asug{display:none}.asug{display:flex;flex-wrap:wrap;gap:6px;padding:0 12px 8px}.asug button{background:#eef2f6;border:1px solid #dde3ea;border-radius:14px;padding:4px 10px;font-size:12px;cursor:pointer;color:#37474f;text-align:left}
.asug button:hover{background:#e3f2fd;border-color:#90caf9}
.aif{border-top:1px solid #e3e8ee;padding:8px 10px;display:flex;gap:8px;align-items:flex-end}.aif textarea{flex:1;min-height:38px;max-height:140px;resize:none;border:1px solid #cfd8dc;border-radius:8px;padding:8px;font:13px/1.4 inherit}
.aif button{background:#1565c0;color:#fff;border:0;border-radius:8px;padding:9px 14px;font-weight:700;cursor:pointer}.aif button.stop{background:#c62828}
.afoot{font-size:11px;color:#90a4ae;padding:0 12px 8px}
.empty-ai{color:#78909c;font-size:13px}.empty-ai b{color:#37474f}
button.askai{font-size:11px;font-weight:700;border:1px solid #90caf9;background:#e3f2fd;color:#0d47a1;border-radius:10px;padding:1px 8px;cursor:pointer;margin-left:6px}
button.askai:hover{background:#bbdefb}a.askai-next{margin-left:8px;font-size:13px;font-weight:700}
dialog#aihint{width:min(560px,94vw);border:1px solid #cfd8dc;border-radius:12px;padding:16px 18px}dialog#aihint code{background:#eef2f6;padding:2px 6px;border-radius:4px;font-size:12px;word-break:break-all}
dialog#aihint ol{padding-left:20px}dialog#aihint li{margin:6px 0}dialog#aihint .row{display:flex;justify-content:flex-end;gap:8px;margin-top:10px}
dialog#aihint button{background:#1565c0;color:#fff;border:0;border-radius:6px;padding:6px 12px;font-weight:600;cursor:pointer}
@media (max-width:900px){#aibub{right:16px;bottom:16px}#aipanel{right:8px;bottom:8px;height:calc(100vh - 80px)}}
@media print{#aibub,#aipanel,#aicall,button.askai,a.askai-next{display:none!important}}
html[data-theme=dark] #aipanel,html[data-theme=dark] dialog#aihint{background:#161d25;border-color:#2a3440;color:#d7dee6}html[data-theme=dark] .aph{background:#1a222b;border-color:#2a3440}
html[data-theme=dark] .aph select,html[data-theme=dark] .aif textarea{background:#0f141a;color:#d7dee6;border-color:#2a3440}html[data-theme=dark] .aif,html[data-theme=dark] .aph{border-color:#2a3440}
html[data-theme=dark] .amsg.a{background:#1d2630;border-color:#2a3440}html[data-theme=dark] .amsg.a code{background:#2a3440}html[data-theme=dark] .asug button,html[data-theme=dark] .amsg .acts button{background:#1d2630;border-color:#2a3440;color:#d7dee6}
html[data-theme=dark] button.askai{background:#10243a;border-color:#1f4a75;color:#90caf9}html[data-theme=dark] .empty-ai b{color:#d7dee6}html[data-theme=dark] dialog#aihint code{background:#1d2630}
"""

EXTRA6_JS = r"""
/* ===== v6: Ask AI — talks to report_server.py, which runs the local Cursor agent (read-only ask mode) ===== */
const AIB=window.__AI_BRIDGE||null;let AIST=null,AICTX=null,AIABORT=null,AIBUSY=false;const AIKEY=KEY+'-ai';
const AIS=LS.get(AIKEY,{});
function aiSave(){const o={};Object.entries(AIS).forEach(([k,v])=>{o[k]={chat:v.chat,msgs:(v.msgs||[]).slice(-24)};});LS.set(AIKEY,o);}
async function aiCheck(force){if(!AIB||location.protocol==='file:'){aiOff(location.protocol==='file:'?'file':'noserver');return;}
 try{const r=await fetch('/api/ai/status'+(force?'?refresh=1':''),{headers:{'X-Report-Token':AIB.token}});AIST=await r.json();}catch(e){AIST={available:false,reason:'noserver'};}
 if(AIST.available&&AIST.enabled!==false)aiOn();else aiOff(AIST.enabled===false?'disabled':(AIST.reason||'unknown'));}
function aiOn(){document.body.classList.add('ai-on');paintAskButtons();
 const n=document.getElementById('aibubacct');if(n)n.title='Cursor agent · '+(AIST.account||'')+(AIST.team?' · '+AIST.team:'');
 if(!LS.get(KEY+'-aicall',false)){const c=document.getElementById('aicall');if(c)c.hidden=false;}}
function aiOff(why){document.body.classList.remove('ai-on');window.__AIWHY=why;}
function dismissCall(){const c=document.getElementById('aicall');if(c)c.hidden=true;LS.set(KEY+'-aicall',true);}
function showAiHint(){const d=document.getElementById('aihint');const why=window.__AIWHY||'file';
 document.getElementById('aihintwhy').textContent={file:'This report was opened as a file, so it cannot reach the Cursor agent on your Mac.',
  noserver:'The report helper is not running.','not-logged-in':'The Cursor agent is installed but not logged in.','not-installed':'The Cursor agent CLI is not installed on this Mac.',
  disabled:'AI help is turned off for this repository (.merge-guard.json → ai_help.enabled).'}[why]||(AIST&&AIST.hint)||'AI help is not available.';
 if(d.showModal)d.showModal();else d.setAttribute('open','');}

/* context: the focused card, or the whole report */
function aiKey(c){return c?('card:'+c):'report';}
function cardTitle(id){const c=document.getElementById(id);return c?((c.querySelector('.ttl')||{}).textContent||''):'';}
function openAI(cardId,question){if(!document.body.classList.contains('ai-on'))return showAiHint();dismissCall();
 AICTX=cardId===undefined?(CUR?CUR.id:null):cardId;const p=document.getElementById('aipanel');p.hidden=false;document.getElementById('aibub').style.visibility='hidden';
 paintCtxSel();paintThread();const ta=document.getElementById('aiq');if(question){ta.value=question;askAI();}else setTimeout(()=>ta.focus(),30);}
function closeAI(){document.getElementById('aipanel').hidden=true;document.getElementById('aibub').style.visibility='';}
function paintCtxSel(){const sel=document.getElementById('aictx');const ids=ALLCARDS.map(c=>c.id);
 sel.innerHTML='<option value="">Whole report</option>'+ids.map(id=>`<option value="${id}">${id} — ${esc(cardTitle(id)).slice(0,40)}</option>`).join('');sel.value=AICTX||'';}
function suggestions(){if(!AICTX)return['What still blocks this merge, in order of importance?','Explain the riskiest change in plain words','Which cards should a tester check first?','Summarise this merge for the team in 5 bullets'];
 const c=document.getElementById(AICTX);const q=['Explain this change simply — what does each side do?','What breaks if I keep current code?','Which option is safest, and why?'];
 if(c&&c.querySelector('pre.proposal'))q.push("Is the AI's merged version correct?");
 if(c&&/missing after merge/.test(c.textContent))q.unshift('Why is a line missing after the merge, and how do I restore it?');
 if(c&&/disagree/.test(c.querySelector('.verdict')?.textContent||''))q.unshift('The second check disagrees — who is right?');
 q.push('Draft a short note for this decision');return q.slice(0,5);}

/* tiny, safe markdown (everything is escaped first) + "Open in Cursor" links for path:line */
let PATHIX=null;
function fullPath(p){if(p.startsWith('/')||p.includes('/'))return p;
 if(!PATHIX){PATHIX={};document.querySelectorAll('.spath code, .path code, details.calls code, #quality td code').forEach(c=>{const t=c.textContent.trim().split(':')[0];if(t.includes('/')){const b=t.split('/').pop();if(!PATHIX[b])PATHIX[b]=t;}});}
 return PATHIX[p]||null;}
function cursorLink(path,line){const ws=(AIST&&AIST.workspace)||(AIB&&AIB.workspace)||'';const fp=fullPath(path);if(!fp)return null;const abs=fp.startsWith('/')?fp:ws.replace(/\/$/,'')+'/'+fp;
 return `cursor://file${encodeURI(abs)}${line?':'+line:''}`;}
function linkify(codeText){const m=codeText.match(/^([^\s`:]+(?: [^\s`:]+)*\.(?:swift|mm?|h|kt|java|plist|json|xib|storyboard|pbxproj|yml|md))(?::(\d+)(?:[-–]\d+)?)?$/);
 const u=m&&cursorLink(m[1],m[2]);return u?`<a class="cur" href="${u}" title="Open in Cursor">${esc(codeText)}</a>`:`<code>${esc(codeText)}</code>`;}
function inlineMd(t){return esc(t).replace(/`([^`]+)`/g,(m,c)=>linkify(c.replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"').replace(/&amp;/g,'&')))
 .replace(/\*\*([^*]+)\*\*/g,'<b>$1</b>').replace(/(^|[\s(])([A-Za-z0-9_./+-]+\.(?:swift|mm?|h|kt|java)):(\d+)/g,(m,p,f,l)=>{const u=cursorLink(f,l);return u?`${p}<a class="cur" href="${u}" title="Open in Cursor">${f}:${l}</a>`:m;});}
function md(t){const out=[];const lines=String(t||'').split('\n');let i=0,list=null;const flush=()=>{if(list){out.push(`<${list.t}>`+list.items.map(x=>'<li>'+inlineMd(x)+'</li>').join('')+`</${list.t}>`);list=null;}};
 while(i<lines.length){const l=lines[i];
  if(/^```/.test(l)){flush();const buf=[];i++;while(i<lines.length&&!/^```/.test(lines[i]))buf.push(lines[i++]);i++;out.push('<pre>'+esc(buf.join('\n'))+'</pre>');continue;}
  const b=l.match(/^\s*[-*•]\s+(.*)/),n=l.match(/^\s*\d+[.)]\s+(.*)/);
  if(b||n){const t=b?'ul':'ol';if(!list||list.t!==t){flush();list={t,items:[]};}list.items.push((b||n)[1]);i++;continue;}
  flush();if(l.trim()){const h=l.match(/^#{1,4}\s+(.*)/);out.push(h?'<p><b>'+inlineMd(h[1])+'</b></p>':'<p>'+inlineMd(l)+'</p>');}i++;}
 flush();return out.join('');}

function paintThread(){const box=document.getElementById('aimsgs');const th=AIS[aiKey(AICTX)];const msgs=(th&&th.msgs)||[];
 if(!msgs.length){box.innerHTML=`<div class="empty-ai">${AICTX?`Ask anything about <b>${AICTX}</b> — ${esc(cardTitle(AICTX))}.`:'Ask anything about <b>this merge</b>.'}<br>The Cursor agent reads the card and the repository (read-only) and answers here.</div>`;}
 else box.innerHTML=msgs.map((m,ix)=>msgHtml(m,ix)).join('');
 document.getElementById('aisug').innerHTML=suggestions().map(q=>`<button type="button">${esc(q)}</button>`).join('');
 box.scrollTop=box.scrollHeight;}
function msgHtml(m,ix){if(m.role==='u')return `<div class="amsg u">${esc(m.text)}</div>`;
 if(m.role==='e')return `<div class="amsg err">${esc(m.text)}</div>`;
 const th=AIS[aiKey(AICTX)]||{};
 return `<div class="amsg a" data-ix="${ix}">${m.tools&&m.tools.length?`<div class="tools">🔎 ${esc(m.tools.slice(-3).join(' · '))}</div>`:''}${md(m.text)}`+
  `<div class="acts"><button type="button" data-act="copy">Copy</button>${AICTX?'<button type="button" data-act="note">Add to notes</button>':''}<button type="button" data-act="term" title="Copy a terminal command that continues this conversation">Continue in terminal</button></div>`+
  `<div class="meta">Cursor agent${m.ms?` · ${(m.ms/1000).toFixed(0)} s`:''}${th.chat?' · chat '+th.chat.slice(0,8):''}</div></div>`;}

async function askAI(){if(AIBUSY)return;const ta=document.getElementById('aiq');const q=ta.value.trim();if(!q)return;ta.value='';
 const k=aiKey(AICTX);const th=AIS[k]=AIS[k]||{chat:'',msgs:[]};th.msgs.push({role:'u',text:q});aiSave();paintThread();
 const box=document.getElementById('aimsgs');const live=document.createElement('div');live.className='amsg a';live.innerHTML='<div class="tools"></div><div class="body"><span class="athink"><i></i><i></i><i></i></span> <span class="muted">Cursor agent is reading the code…</span></div>';box.appendChild(live);box.scrollTop=box.scrollHeight;
 AIBUSY=true;document.getElementById('aipanel').classList.add('busy');const btn=document.getElementById('aisend');btn.textContent='Stop';btn.classList.add('stop');AIABORT=new AbortController();
 let text='',tools=[],done=null,err=null;
 try{const r=await fetch('/api/ai/ask',{method:'POST',signal:AIABORT.signal,headers:{'Content-Type':'application/json','X-Report-Token':AIB.token},
   body:JSON.stringify({scope:AICTX?'card':'report',card_id:AICTX||'',question:q,chat_id:th.chat||''})});
  if(!r.ok||!r.body){const j=await r.json().catch(()=>({}));throw new Error(j.error||('HTTP '+r.status));}
  const rd=r.body.getReader(),dec=new TextDecoder();let buf='';
  for(;;){const {value,done:fin}=await rd.read();if(fin)break;buf+=dec.decode(value,{stream:true});let p;
   while((p=buf.indexOf('\n\n'))>=0){const blk=buf.slice(0,p);buf=buf.slice(p+2);const ev=(blk.match(/^event: (.*)$/m)||[])[1],data=JSON.parse((blk.match(/^data: (.*)$/m)||[,'{}'])[1]);
    if(ev==='meta'){th.chat=data.chat_id;aiSave();}
    else if(ev==='tool'){tools.push(data.name+(data.detail?' '+data.detail.split('/').pop():''));live.querySelector('.tools').textContent='🔎 '+tools.slice(-3).join(' · ');}
    else if(ev==='delta'){text+=data.text;live.querySelector('.body').innerHTML=md(text);box.scrollTop=box.scrollHeight;}
    else if(ev==='done'){done=data;}else if(ev==='error'){err=data.message;}}}
 }catch(e){if(e.name!=='AbortError')err=String(e.message||e);else err='Stopped.';}
 AIBUSY=false;document.getElementById('aipanel').classList.remove('busy');btn.textContent='Send';btn.classList.remove('stop');AIABORT=null;
 if(done&&!done.error)th.msgs.push({role:'a',text:done.text||text,tools,ms:done.ms});else if(text)th.msgs.push({role:'a',text,tools});
 if(err||(done&&done.error))th.msgs.push({role:'e',text:err||'The Cursor agent reported an error.'});
 aiSave();paintThread();}

document.addEventListener('click',e=>{
 const s=e.target.closest('#aisug button');if(s){document.getElementById('aiq').value=s.textContent;askAI();return;}
 const a=e.target.closest('#aimsgs .acts button');if(a){const ix=+a.closest('.amsg').dataset.ix;const th=AIS[aiKey(AICTX)];const m=th&&th.msgs[ix];if(!m)return;
  if(a.dataset.act==='copy')copyText(m.text,'Answer');
  else if(a.dataset.act==='term')copyText(`cursor-agent --resume ${th.chat} --workspace "${(AIST&&AIST.workspace)||''}"`,'Terminal command');
  else if(a.dataset.act==='note'){const t=document.querySelector(`textarea[data-notes="${AICTX}"]`);if(!t)return toast('This card has no notes field');
   const add='[AI help] '+m.text.replace(/\s+/g,' ').trim().slice(0,600);t.value=(t.value.trim()?t.value.trim()+'\n':'')+add;t.dispatchEvent(new Event('input',{bubbles:true}));
   toggleCard(document.getElementById(AICTX),true);toast('Added to the notes of '+AICTX+' — review and edit before exporting');}
  return;}
 const k=e.target.closest('button.askai');if(k){e.preventDefault();openAI(k.closest('.card').id);return;}
 const n=e.target.closest('a.askai-next');if(n){e.preventDefault();openAI(n.dataset.card||null,n.dataset.q||'');}});
function paintAskButtons(){if(!document.body.classList.contains('ai-on'))return;ALLCARDS.forEach(c=>{if(c.querySelector('button.askai'))return;const b=document.createElement('button');b.type='button';b.className='askai';
 b.textContent='✦ Ask AI';b.title='Ask the Cursor agent about this card (q)';const h=c.querySelector('header');const asg=h.querySelector('.asg');h.insertBefore(b,asg||h.querySelector('.rs')||null);});
 const nx=document.getElementById('startnext');if(nx&&!nx.querySelector('.askai-next')){const go=nx.querySelector('a.go');const id=go?go.getAttribute('href').slice(1):'';const card=/^M-\d+$/.test(id)?id:'';
  const a=document.createElement('a');a.href='#';a.className='askai-next';a.dataset.card=card;a.dataset.q=card?'How do I resolve this, step by step?':'What should I do next to get this merge ready?';
  a.textContent='✦ Ask AI how to fix this';a.title='Opens the AI help panel with this question';nx.appendChild(a);}}
const _paintStart6=paintStart;paintStart=function(){_paintStart6();paintAskButtons();};
document.getElementById('aictx').addEventListener('change',e=>{AICTX=e.target.value||null;paintThread();});
document.getElementById('aiq').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();askAI();}if(e.key==='Escape')closeAI();});
document.getElementById('aisend').addEventListener('click',()=>{if(AIBUSY&&AIABORT)AIABORT.abort();else askAI();});
document.addEventListener('keydown',e=>{if(e.key!=='q'||e.metaKey||e.ctrlKey||e.altKey||e.target.matches('textarea,input:not([type=radio]):not([type=checkbox]),select'))return;
 e.stopImmediatePropagation();e.preventDefault();openAI(CUR?CUR.id:null);},true);
window.addEventListener('load',()=>aiCheck(false));
"""

EXTRA7_CSS = r"""
/* ===== v7: phones & tablets ===== */
.mname{display:none}
@media (max-width:900px){
 .wrap{padding:14px 12px}
 table.list,table.pairs,table.devt{display:block;overflow-x:auto;-webkit-overflow-scrolling:touch;max-width:100%}
 table.list td,table.list th{min-width:90px}
 #aipanel{left:8px;right:8px;width:auto}
 .cols,.cols.cols3,.cols.cols4,body.nobase:not(.diff-inline) .cols.cols4{grid-template-columns:1fr!important}
 .cols.tabbed>div{display:none}.cols.tabbed>div.on{display:block}
 .ctabs{display:flex;gap:0;border:1px solid #cfd8dc;border-radius:8px;overflow:hidden;margin:8px 0 6px}
 .ctabs button{flex:1;background:#fff;border:0;border-left:1px solid #cfd8dc;padding:8px 4px;font:600 12.5px/1.1 inherit;color:#37474f;cursor:pointer}
 .ctabs button:first-child{border-left:0}.ctabs button.on{background:#546e7a;color:#fff}
 .cols.tabbed h5{display:none}
}
@media (max-width:700px){
 body{font-size:14px;-webkit-text-size-adjust:100%}
 /* compact sticky bar: row 1 = title + status, row 2 = search + actions */
 .bar{padding:6px 10px}.brow{display:grid;grid-template-columns:minmax(0,1fr) auto auto auto auto;gap:6px;align-items:center}
 .bar .rid{grid-column:1/4;font-size:13px}#rready{grid-column:4/6;justify-self:end;font-size:11px}#rstat,.bar .grow,.bar #by,.bar #qcount{display:none}
 .bar #q{grid-column:1;width:100%;min-width:0}.bar .lg{display:none}
 .bar button,summary.btn{padding:8px 11px;min-height:38px}
 .bar input,.bar select,.pop select,.pop input,textarea,#aiq{font-size:16px}   /* no iOS zoom on focus */
 /* menus become sheets under the bar */
 .pop,.mpop{position:fixed;top:calc(var(--bar,90px) + 4px);left:8px;right:8px;width:auto;min-width:0;max-height:calc(100vh - var(--bar,90px) - 16px)}
 .mname{display:flex;flex-direction:column;gap:3px;font-size:12px;font-weight:600;color:#5b6775;padding:0 4px 6px}
 .mname input{border:1px solid #cfd8dc;border-radius:6px;padding:7px 8px}
 .mpop .mi,#rsave button{min-height:40px}.seg button{padding:7px 10px}.mpop kbd{display:none}
 /* page */
 h1{font-size:20px;line-height:1.3}h1 code{word-break:break-all}h2{font-size:17px;margin:24px 0 10px}
 #start{padding:12px 14px}#start .sh{font-size:17px}#startnext{font-size:14px}#startnext a.go{display:inline-block;margin:6px 6px 0 0}
 .tiles .tile{min-width:calc(50% - 5px)}
 /* cards */
 .card{padding:12px;border-radius:10px}.card header{gap:6px}.card header .ttl{flex:1 1 100%;order:5}
 .card header .rs,.card header button.asg,.card header button.askai{margin-left:0}
 .verdict{font-size:13.5px}.devs{grid-template-columns:1fr}
 .opts{flex-direction:column;align-items:stretch}.opt{padding:9px 12px;border-radius:10px}.confirm{padding:6px 0}
 table.code{font-size:11.5px}td.who{display:none}
 .why .meter{width:80px}
 /* AI */
 #aibub{right:14px;bottom:14px;padding:0;width:54px;height:54px;justify-content:center;border-radius:50%;font-size:22px}#aibub span:first-child{font-size:0}
 #aibub span:first-child::before{content:"✦";font-size:22px}#aibub .k{display:none}
 #aicall{right:14px;bottom:78px;width:calc(100vw - 28px);max-width:320px}
 #aipanel{left:0;right:0;bottom:0;top:calc(var(--bar,90px));height:auto;border-radius:14px 14px 0 0}
 .amsg.u{max-width:92%}
 #khelp{left:10px;right:10px;bottom:10px}
 dialog#aihint{padding:14px}
}
body:has(details.menu[open]) #aibub,body:has(details.menu[open]) #aicall{display:none!important}
@media (hover:none) and (pointer:coarse){.mpop .mi[onclick*="toggleHelp"]{display:none}}
@media (hover:none){.tip{width:20px;height:20px;font-size:12px}.tip:hover::after{content:none}.tip:focus::after{content:attr(data-tip)}a.iid:hover::after{content:none}}
html[data-theme=dark] .ctabs{border-color:#2a3440}html[data-theme=dark] .ctabs button{background:#161d25;color:#d7dee6;border-color:#2a3440}html[data-theme=dark] .ctabs button.on{background:#3b4a57}
html[data-theme=dark] .mname input{background:#0f141a;color:#d7dee6;border-color:#2a3440}
"""

EXTRA7_JS = r"""
/* ===== v7: phones — code columns as tabs, name field in the ⋯ menu ===== */
const MQP=window.matchMedia('(max-width:900px)');
function tabLabel(div){if(div.classList.contains('c-base'))return 'Base';if(div.classList.contains('c-src'))return 'Incoming';if(div.classList.contains('c-tgt'))return 'Current';if(div.classList.contains('c-res'))return 'Result';return 'Code';}
function tabify(){document.querySelectorAll('.cols').forEach(cols=>{const kids=[...cols.children].filter(x=>x.tagName==='DIV');
 if(MQP.matches){if(cols.classList.contains('tabbed'))return;cols.classList.add('tabbed');
  const bar=document.createElement('div');bar.className='ctabs';bar.setAttribute('role','tablist');
  const pick=kids.find(k=>k.classList.contains('c-src'))||kids[0];
  kids.forEach(k=>{const b=document.createElement('button');b.type='button';b.textContent=tabLabel(k);b.setAttribute('role','tab');
   b.onclick=()=>{kids.forEach(x=>x.classList.toggle('on',x===k));bar.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b));};
   bar.appendChild(b);if(k===pick){k.classList.add('on');b.classList.add('on');}});
  cols.parentNode.insertBefore(bar,cols);}
 else if(cols.classList.contains('tabbed')){cols.classList.remove('tabbed');kids.forEach(k=>k.classList.remove('on'));const t=cols.previousElementSibling;if(t&&t.classList.contains('ctabs'))t.remove();}});}
if(MQP.addEventListener)MQP.addEventListener('change',()=>{tabify();barH();});
const by2=document.getElementById('by2');
if(by2){const by=document.getElementById('by');
 document.getElementById('mmenu').addEventListener('toggle',()=>{by2.value=by.value;});
 /* read-only mirror */}
window.addEventListener('load',()=>{tabify();barH();});
"""

EXTRA8_CSS = r"""
/* ===== v8: commit links ===== */
a.sha{text-decoration:none;color:inherit}a.sha code{color:#1565c0;border-bottom:1px dashed #90caf9}a.sha:hover code{background:#e3f2fd}
a.sha:not(:has(code)){color:#1565c0;border-bottom:1px dashed #90caf9;font-family:SFMono-Regular,Menlo,monospace;font-size:.92em}
a.sha::after{content:"↗";font-size:10px;margin-left:2px;color:#90a4ae}span.sha.nolink{cursor:help}
html[data-theme=dark] a.sha code,html[data-theme=dark] a.sha:not(:has(code)){color:#7cb7ff;border-color:#1f4a75}html[data-theme=dark] a.sha:hover code{background:#10243a}
@media print{a.sha::after{content:none}}
"""

EXTRA8_JS = r"""
/* ===== v8: commit ids in AI answers open the commit on the git host ===== */
function shaLink(x){if(typeof SHA_LINKS==='undefined'||!/^[0-9a-f]{7,40}$/.test(x))return null;const k=Object.keys(SHA_LINKS).find(s=>s.startsWith(x));return k?SHA_LINKS[k]:null;}
const _inlineMd8=inlineMd;inlineMd=function(t){let h=_inlineMd8(t);
 h=h.replace(/<code>([0-9a-f]{7,40})<\/code>/g,(m,x)=>{const u=shaLink(x);return u?`<a class="sha" href="${u}" target="_blank" rel="noopener noreferrer" title="Open commit"><code>${x}</code></a>`:m;});
 let inA=0;return h.split(/(<[^>]+>)/).map(p=>{if(p.startsWith('<')){if(/^<a\b/i.test(p))inA++;else if(/^<\/a>/i.test(p))inA=Math.max(0,inA-1);return p;}return inA?p:p.replace(/(^|[^\w/#.-])([0-9a-f]{7,40})(?![\w-])/g,(m,pre,x)=>{const u=shaLink(x);return u?`${pre}<a class="sha" href="${u}" target="_blank" rel="noopener noreferrer" title="Open commit">${x}</a>`:m;});}).join('');};
"""

EXTRA9_CSS = r"""
/* ===== v9: reviewer identity (mandatory, read-only) ===== */
.bar #by{cursor:default;background:#f4f6f8;font-weight:600;color:#37474f;padding-left:24px;
 background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath fill='%2378909c' d='M8 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6zm0 1c-2.7 0-5 1.3-5 3v1h10v-1c0-1.7-2.3-3-5-3z'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:6px center;background-size:14px}
body.noid .bar #by{cursor:pointer;background-color:#fff3e0;border-color:#ffb74d;color:#8a4b00}
body.noid .decision,body.noid .qa{opacity:.55}body.noid .decision *,body.noid .qa *{cursor:not-allowed}
#idnote{display:none;background:#fff8e1;border:1px solid #ffe082;border-radius:8px;padding:8px 12px;margin:10px 0;font-size:13.5px}body.noid #idnote{display:block}
dialog#whodlg{width:min(440px,94vw);border:1px solid #cfd8dc;border-radius:12px;padding:18px 20px}dialog#whodlg::backdrop{background:#0f172066}
dialog#whodlg button{background:#1565c0;color:#fff;border:0;border-radius:8px;padding:8px 14px;font-weight:700;cursor:pointer}dialog#whodlg button:disabled{opacity:.45;cursor:not-allowed}
.mname input{background:#f4f6f8}
html[data-theme=dark] .bar #by,html[data-theme=dark] .mname input{background-color:#1d2630;color:#d7dee6}
html[data-theme=dark] body.noid .bar #by{background-color:#2b2510;color:#ffcf70;border-color:#5c4b14}html[data-theme=dark] #idnote{background:#2b2510;border-color:#5c4b14}
html[data-theme=dark] dialog#whodlg{background:#161d25;color:#d7dee6;border-color:#2a3440}html[data-theme=dark] #whoname{background:#0f141a;color:#d7dee6;border-color:#2a3440}
"""

EXTRA9_JS = r"""
/* ===== v9: reviewer identity — from git config via report_server.py, else asked once; never editable ===== */
const IDKEY='merge-report-reviewer';
function identity(){const g=AIB&&AIB.reviewer;if(g&&g.name)return {name:g.name,email:g.email||'',source:'git config'};
 const s=LS.get(IDKEY,null);return s&&s.name?{name:s.name,email:'',source:'entered in this browser'}:null;}
function applyIdentity(){const id=identity(),by=document.getElementById('by'),by2=document.getElementById('by2');
 document.body.classList.toggle('noid',!id);
 by.value=id?id.name:'';by.title=id?`Reviewer: ${id.name}${id.email?' <'+id.email+'>':''} — from ${id.source}. Saved with every decision; not editable.`:'No reviewer yet — click to set your name';
 if(by2)by2.value=by.value;
 if(id){try{const k=JSON.parse(localStorage.getItem(KEY)||'null')||{};if(k.by!==id.name){k.by=id.name;localStorage.setItem(KEY,JSON.stringify(k));}}catch(e){}}
 if(typeof refresh==='function'&&typeof CARDS!=='undefined')refresh();}
function needId(){if(identity())return false;askWho();return true;}
function askWho(){const d=document.getElementById('whodlg');if(d.open)return;const i=document.getElementById('whoname');i.value='';document.getElementById('whook').disabled=true;
 if(d.showModal)d.showModal();else d.setAttribute('open','');setTimeout(()=>i.focus(),30);}
document.getElementById('whoname').addEventListener('input',e=>{document.getElementById('whook').disabled=e.target.value.trim().length<2;});
document.getElementById('whoname').addEventListener('keydown',e=>{if(e.key==='Enter'&&!document.getElementById('whook').disabled){e.preventDefault();document.getElementById('whook').click();}});
document.getElementById('whook').addEventListener('click',()=>{const n=document.getElementById('whoname').value.trim().replace(/\s+/g,' ');if(n.length<2)return;
 if(!confirm(`Review as “${n}”?\n\nThis name is saved with your decisions and can't be changed later in this browser.`))return;
 LS.set(IDKEY,{name:n,at:new Date().toISOString()});document.getElementById('whodlg').close();applyIdentity();toast('Reviewing as '+n);});
document.getElementById('whobrowse').addEventListener('click',e=>{e.preventDefault();document.getElementById('whodlg').close();});
document.getElementById('whodlg').addEventListener('cancel',e=>{});   /* Esc = just look around */
document.getElementById('by').addEventListener('click',()=>{if(!identity())askWho();});

/* block every review action until a reviewer is set */
function guardEvt(e){if(identity())return;const t=e.target;
 if(t.closest('.decision, .qa, button.asg')||t.closest('button[onclick^="exportJson"]')||t.closest('[data-act="note"]')){e.preventDefault();e.stopImmediatePropagation();if(t.blur)t.blur();askWho();}}
['click','mousedown','keydown','focusin'].forEach(ev=>document.addEventListener(ev,e=>{if(ev==='keydown'&&!(e.target.closest&&e.target.closest('.decision, .qa')))return;guardEvt(e);},true));
const _choose9=choose;choose=function(v){if(needId())return;_choose9(v);};
const _exportJson9=exportJson;exportJson=function(){if(needId())return;_exportJson9();};
const _toggleAssign9=toggleAssign;toggleAssign=function(id){if(needId())return;_toggleAssign9(id);};
document.addEventListener('keydown',e=>{if(e.key==='r'&&!identity()&&!e.target.matches('textarea,input,select')&&CUR){e.preventDefault();e.stopImmediatePropagation();askWho();}},true);

/* the reviewer always wins over names restored from saved progress */
const _restore9=restoreLocal;restoreLocal=function(L){_restore9(L);applyIdentity();};
const _load9=load;load=function(){_load9();applyIdentity();};
const _buildOut9=buildOut;buildOut=function(){const o=_buildOut9();const id=identity();if(id){o.decided_by=id.name;o.decided_by_email=id.email||undefined;o.decided_by_source=id.source;}return o;};
window.addEventListener('load',()=>{applyIdentity();if(!identity())setTimeout(askWho,600);});
"""

TRACKER_BAR = '<span id="rsave" style="display:inline-flex;gap:6px;align-items:center"></span><span id="rready" class="chip"></span><span id="rstat" class="chip"></span><select id="rfilter" title="Show cards"><option value="all">Status: all</option><option value="pend">Status: pending</option><option value="done">Status: reviewed</option><option value="conf">Status: reviewers disagree</option></select><select id="rdev" title="Filter by developer"><option value="">Developer: everyone</option></select><button class="sec" onclick="nextPending()">Next pending ▶</button><button class="sec" onclick="showPendingList()">Pending list</button><button class="sec" onclick="document.getElementById(\'importf\').click()">Import decisions (.json)</button><input type="file" id="importf" accept=".json,application/json" multiple style="display:none">'


EXTRA_JS = r"""
/* ===== Syntax highlighting (Swift / Objective-C / Kotlin-ish), done on the client so the report stays small ===== */
const KW=new Set('func var let if else guard return self Self true false nil null class struct enum protocol extension import case switch default for while in do try catch throw throws rethrows async await static private fileprivate internal public open override final lazy weak unowned init deinit super where is as some any inout mutating get set willSet didSet typealias associatedtype defer break continue repeat fallthrough convenience required dynamic optional indirect nonisolated actor @objc YES NO void id instancetype nonatomic strong assign readonly val fun object when'.split(' '));
const TOK=/(\/\/.*$|\/\*.*?\*\/)|("(?:\\.|[^"\\])*")|(#\s*(?:if|elseif|else|endif|available|selector|keyPath|warning|error|import|define|pragma)\b[^\n]*)|(@\w+)|(\b\d[\d_.]*\b)|(\b[A-Za-z_]\w*\b)/g;
function hl(t){let out='',i=0;t.replace(TOK,(m,c,s,d,a,n,w,off)=>{out+=esc(t.slice(i,off));i=off+m.length;
 out+=c?`<span class="hl-c">${esc(m)}</span>`:s?`<span class="hl-s">${esc(m)}</span>`:d?`<span class="hl-d">${esc(m)}</span>`:a?`<span class="hl-a">${esc(m)}</span>`:n?`<span class="hl-n">${m}</span>`:
  KW.has(w)?`<span class="hl-k">${w}</span>`:/^[A-Z]/.test(w)?`<span class="hl-t">${w}</span>`:w;return m;});return out+esc(t.slice(i));}
function highlightAll(root){(root||document).querySelectorAll('td.lc:not([data-hl]),pre.proposal:not([data-hl])').forEach(el=>{el.dataset.hl=1;const t=el.textContent;if(t.trim())el.innerHTML=hl(t);});}

/* ===== Result preview: what the file will contain for the chosen option ===== */
function resultFor(card){const box=card.querySelector('.c-res .resbody');if(!box)return;const dec=card.querySelector('.decision');
 const r=dec&&dec.querySelector('input[type=radio]:checked');const ch=r?r.value:(dec?null:'SOURCE');
 const take=sel=>{const t=card.querySelector(sel+' table.code');return t?t.outerHTML:'<div class="code empty">— not present —</div>';};
 const prop=card.querySelector('pre.proposal');const notes=dec?dec.querySelector('textarea').value.trim():'';
 let lab='',html='';
 if(!ch){html='<div class="code empty">Pick an option to preview the result.</div>';}
 else if(ch==='SOURCE'){lab='Source lines replace target here';html=take('.c-src');}
 else if(ch==='TARGET'){lab='Target kept — the source change is dropped';html=take('.c-tgt');}
 else if(ch==='AI'){lab='AI proposal (source behaviour inside target code)';html=prop?prop.outerHTML:'<div class="code empty">No proposed code on this card.</div>';}
 else if(ch==='BOTH'){lab=prop?'Proposed code keeping both behaviours':'Both kept — merge by hand as described in the notes';html=prop?prop.outerHTML:take('.c-tgt')+take('.c-src');}
 else {lab='Custom — follows the notes';html='<pre class="summary">'+esc(notes||'(no notes yet — write what to keep)')+'</pre>';}
 box.innerHTML=(lab?`<div class="rlab">${esc(lab)}${dec?'':' (auto-applied)'}</div>`:'')+html;
 box.querySelectorAll('[id]').forEach(x=>x.removeAttribute('id'));}
document.addEventListener('change',e=>{const c=e.target.closest('.card');if(c&&e.target.type==='radio')resultFor(c);});
document.addEventListener('input',e=>{const c=e.target.closest('.card');if(c&&e.target.tagName==='TEXTAREA')resultFor(c);});

/* ===== Deep links: #M-0005 or #M-0005-source-L201 opens its section and scrolls there ===== */
function openTo(id,flash){const el=document.getElementById(id);if(!el)return false;for(let n=el.parentElement;n;n=n.parentElement)if(n.tagName==='DETAILS')n.open=true;
 const card=el.closest('.card')||el;card.style.display='';setFocus(card,false);el.scrollIntoView({block:el===card?'start':'center'});
 if(flash!==false){const f=el.tagName==='TR'?'flash':'flashc';el.classList.remove(f);void el.offsetWidth;el.classList.add(f);}return true;}
function onHash(){const h=decodeURIComponent(location.hash.slice(1));if(h&&/^M-\d+/.test(h)){openTo(h);setTimeout(()=>openTo(h,false),400);}}
function barH(){const b=document.querySelector('.bar');if(b)document.documentElement.style.setProperty('--bar',b.offsetHeight+'px');}
window.addEventListener('resize',barH);
window.addEventListener('hashchange',onHash);
function cardLink(card){const u=location.href.split('#')[0]+'#'+card.id;copyText(u,'Link to '+card.id);}
document.addEventListener('click',e=>{const a=e.target.closest('a.iid');if(a){e.preventDefault();const c=a.closest('.card');history.replaceState(null,'','#'+c.id);cardLink(c);return;}
 const j=e.target.closest('a[data-jump],a.dep,#minimap a,#areas a.t');if(j&&j.getAttribute('href')){const id=j.getAttribute('href').slice(1);if(openTo(id)){e.preventDefault();history.replaceState(null,'','#'+id);}}
 const an=e.target.closest('#areas a.an');if(an){document.getElementById('rarea').value=an.dataset.area;refresh();}});

/* ===== Keyboard review ===== */
let CUR=null;
function visibleCards(){return [...document.querySelectorAll('.card')].filter(c=>c.offsetParent!==null);}
function setFocus(c,scroll=true){if(CUR)CUR.classList.remove('kfocus');CUR=c;if(!c)return;c.classList.add('kfocus');if(scroll)c.scrollIntoView({behavior:'smooth',block:'start'});paintMinimap();}
function step(d){const v=visibleCards();if(!v.length)return;let i=CUR?v.indexOf(CUR):-1;
 if(i<0){const y=window.scrollY+90;i=v.findIndex(c=>c.getBoundingClientRect().top+window.scrollY>=y);if(i<0)i=v.length-1;if(d<0)i=Math.max(0,i-1);setFocus(v[i]);return;}
 setFocus(v[Math.min(v.length-1,Math.max(0,i+d))]);}
function choose(v){if(!CUR)return toast('Press j to select a card first');const r=CUR.querySelector(`.decision input[value="${v}"]`);
 if(!r)return toast(v+' is not an option on '+CUR.id);r.checked=true;r.dispatchEvent(new Event('change',{bubbles:true}));toast(CUR.id+' → '+v);}
const KEYS={s:'SOURCE',t:'TARGET',b:'BOTH',a:'AI',c:'CUSTOM'};
document.addEventListener('keydown',e=>{const tg=e.target;if(e.metaKey||e.ctrlKey||e.altKey)return;
 if(tg.matches('textarea,input:not([type=radio]):not([type=checkbox]),select')){if(e.key==='Escape')tg.blur();return;}
 const k=e.key;
 if(k==='j')step(1);else if(k==='k')step(-1);
 else if(k==='n'){nextPending();setTimeout(()=>{const y=window.scrollY+100;const c=visibleCards().find(c=>Math.abs(c.getBoundingClientRect().top)<120);if(c)setFocus(c,false);},450);}
 else if(KEYS[k])choose(KEYS[k]);
 else if(k==='Enter'&&CUR&&CUR.dataset.rec)choose(CUR.dataset.rec);
 else if(k==='r'&&CUR){const x=CUR.querySelector('.rv');if(x){x.checked=!x.checked;x.dispatchEvent(new Event('change',{bubbles:true}));toast(CUR.id+(x.checked?' marked reviewed':' unmarked'));}}
 else if(k==='e'&&CUR){const t=CUR.querySelector('.decision textarea');if(t){t.focus();e.preventDefault();}}
 else if(k==='l'&&CUR)cardLink(CUR);
 else if(k==='g'&&CUR){const ev=CUR.querySelector('tr.ev');if(ev){ev.scrollIntoView({block:'center'});ev.classList.remove('flash');void ev.offsetWidth;ev.classList.add('flash');}else toast('No evidence line on this card');}
 else if(k==='d')cycleTheme(true);
 else if(k==='?')toggleHelp();
 else if(k==='Escape'){document.getElementById('khelp').hidden=true;setFocus(null);}
 else return;e.preventDefault();});
function toggleHelp(){const h=document.getElementById('khelp');h.hidden=!h.hidden;}

/* ===== Theme ===== */
const TKEY='merge-report-theme';const mq=window.matchMedia&&matchMedia('(prefers-color-scheme: dark)');
function themePref(){try{return localStorage.getItem(TKEY)||'auto';}catch(e){return 'auto';}}
function applyTheme(){const p=themePref();const dark=p==='dark'||(p==='auto'&&mq&&mq.matches);document.documentElement.dataset.theme=dark?'dark':'light';
 const b=document.getElementById('themebtn');if(b)b.textContent={auto:'◐ Auto',light:'☀ Light',dark:'☾ Dark'}[p];}
function cycleTheme(toggle){const p=themePref();const nx=toggle?(document.documentElement.dataset.theme==='dark'?'light':'dark'):({auto:'light',light:'dark',dark:'auto'}[p]);
 try{localStorage.setItem(TKEY,nx);}catch(e){}applyTheme();}
if(mq&&mq.addEventListener)mq.addEventListener('change',applyTheme);applyTheme();

/* ===== Progress bar, minimap, areas overview (refreshed with the tracker) ===== */
function paintMinimap(){const mm=document.getElementById('minimap');if(!mm||typeof CARDS==='undefined')return;
 if(!mm.childElementCount)mm.innerHTML=CARDS.map(c=>`<a href="#${c.id}" data-id="${c.id}"></a>`).join('');
 [...mm.children].forEach(a=>{const c=BYID[a.dataset.id];const st=c._st||stateOf(c);
  a.className=(st.conflict?'conf':st.done?'done':'')+((c.sec==='decide'||c.sec==='recheck')?' need':'')+(matchDev(c)?'':' hid')+(CUR===c.card?' cur':'');
  a.title=`${c.id} · ${SECNAME[c.sec]||c.sec} · ${st.conflict?'reviewers disagree':st.done?'reviewed':'pending'} · ${c.path}`;});
 const done=CARDS.filter(c=>(c._st||stateOf(c)).done).length;const pb=document.querySelector('#pbar i');if(pb)pb.style.width=(CARDS.length?done*100/CARDS.length:0)+'%';}
function paintAreas(){const box=document.getElementById('areas');if(!box)return;const all=[...document.querySelectorAll('.card[data-area]')];const A={};
 all.forEach(card=>{const a=card.dataset.area;const x=A[a]=A[a]||{n:0,cards:[],risk:0};x.n++;x.cards.push(card);
  if((card.dataset.risk||'').includes('q-filehigh'))x.risk++;});
 const cur=document.getElementById('rarea').value;
 const rows=Object.entries(A).sort((a,b)=>b[1].n-a[1].n).map(([a,x])=>{let pend=0,block=0;
  const chips=x.cards.map(card=>{const c=BYID[card.id];if(!c)return `<a class="t" href="#${card.id}" title="auto-applied">${card.id}</a>`;const st=c._st||stateOf(c);
   if(!st.done||st.conflict){pend++;if(c.sec==='decide'||c.sec==='recheck')block++;}return `<a class="t ${st.conflict?'conf':st.done?'done':'pend'}" href="#${c.id}">${c.id}</a>`;}).join('');
  return `<tr${a===cur?' style="outline:2px solid #7e57c2"':''}><td><a class="an" data-area="${esc(a)}" title="Show only this area">${esc(a)}</a></td><td>${x.n}</td><td>${pend?'<b>'+pend+'</b>':'✓ 0'}</td><td>${block?'<b class="warn">'+block+'</b>':'0'}</td><td>${x.risk?'<span class="qchip lv-high">'+x.risk+' high-risk</span>':''}</td><td>${chips}</td></tr>`;}).join('');
 box.innerHTML=`<details open><summary>Feature areas (${Object.keys(A).length}) — review one area at a time${cur?` · filtered to <b>${esc(cur)}</b> <a href="#" onclick="document.getElementById('rarea').value='';refresh();return false">show all</a>`:''}</summary>`+
  `<table class="list"><tr><th>Area</th><th>Cards</th><th>Pending</th><th>Blocking</th><th>Risk</th><th>Cards</th></tr>${rows}</table></details>`;}
const _refresh2=refresh;refresh=function(){_refresh2();paintMinimap();paintAreas();};

/* ===== Print: open every section, restore afterwards ===== */
let PRINTOPEN=[];
window.addEventListener('beforeprint',()=>{PRINTOPEN=[...document.querySelectorAll('details:not([open])')];PRINTOPEN.forEach(d=>d.open=true);
 document.querySelector('.wrap').dataset.print=RID+' · printed '+new Date().toLocaleString()+' · '+(document.getElementById('rready')||{}).textContent;});
window.addEventListener('afterprint',()=>{PRINTOPEN.forEach(d=>d.open=false);PRINTOPEN=[];});

if('scrollRestoration' in history&&location.hash)history.scrollRestoration='manual';
window.addEventListener('load',()=>{barH();highlightAll();document.querySelectorAll('.card').forEach(resultFor);refresh();onHash();});
"""

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
function matchDev(c){const d=document.getElementById('rdev').value,k=(document.getElementById('rrisk')||{}).value,ar=(document.getElementById('rarea')||{}).value;
 return (!d||c.devs.includes(d))&&(!k||(c.card.dataset.risk||'').split(' ').includes(k))&&(!ar||c.card.dataset.area===ar);}
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
 sel.innerHTML='<option value="">Everyone</option>'+names.map(n=>`<option value="${esc(n)}">${esc(n)} (${dev[n].pend} pending / ${dev[n].t})</option>`).join('');sel.value=cur;
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
 if(f!=='all'||dv||document.getElementById('rrisk').value||document.getElementById('rarea').value)document.querySelectorAll('details:not(.hist)').forEach(d=>{if(d.querySelector('.decision'))d.open=true;});}

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
  IMPORTS[who]={file:f.name,exported_at:j.exported_at||'',decisions:dec,assignments:j.assignments||{},qa:j.qa||{}};done.push(who);}catch(err){bad.push(f.name+': '+err.message);}}
 saveImports();refresh();alert((done.length?'Imported: '+done.join(', '):'Nothing imported')+(bad.length?'\nFailed: '+bad.join('\n'):''));});
const _progress=progress;progress=function(){_progress();refresh();};
document.getElementById('rfilter').addEventListener('change',refresh);document.getElementById('rdev').addEventListener('change',refresh);
if(document.getElementById('rrisk'))document.getElementById('rrisk').addEventListener('change',refresh);
if(document.getElementById('rarea'))document.getElementById('rarea').addEventListener('change',refresh);

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
 if(!FH)h=`<span class="chip" title="Saved in this browser's storage. It is restored when you reopen this file in the same browser.">Saved in this browser${la?' · '+hm(la):''}</span>`+
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


# ================================================================ across merges / review aids (v3)
HIST = {}      # file -> [{id, at, n, cats, branch}] from earlier reports of the same repo
STATE = {}     # render-state.json comparison: {"since": iso, "new": set(ids), "changed": set(ids)}
DECISION_CATS = {"CONFLICT", "SYMBOL_NOT_FOUND", "DELETED_IN_TARGET", "MAPPING_UNCERTAIN", "OPTIMIZED_IN_TARGET", "OPTIMIZED_IN_SOURCE", "NEAR_CHANGE", "RESTRUCTURED"}


def repo_key(d):
    t = d.get("target") or {}
    return os.path.basename((t.get("repo_root") or t.get("folder") or "").rstrip("/"))


def history_scan(folder, d):
    """Files that needed a person in earlier merge reports of the same repository (sibling report folders)."""
    me, key = os.path.basename(folder), repo_key(d)
    out = {}
    for ap in sorted(glob.glob(os.path.join(os.path.dirname(folder), "*", "analysis.json"))):
        rid = os.path.basename(os.path.dirname(ap))
        if rid == me:
            continue
        try:
            o = json.load(open(ap))
        except (OSError, json.JSONDecodeError):
            continue
        if repo_key(o) != key or (o.get("generated_at") or "") > (d.get("generated_at") or "9"):
            continue
        per = {}
        for i in o.get("items") or []:
            cat = i.get("ai_category") or i.get("category")
            if not (i.get("needs_decision_orig") or i.get("needs_decision") or cat in DECISION_CATS):
                continue
            f = i.get("target_path") or i.get("file")
            x = per.setdefault(f, {"id": rid, "at": (o.get("generated_at") or "")[:10], "n": 0, "cats": [],
                                   "branch": f'{(o.get("source") or {}).get("branch")} → {(o.get("target") or {}).get("branch")}'})
            x["n"] += 1
            if cat not in x["cats"]:
                x["cats"].append(cat)
        for f, x in per.items():
            out.setdefault(f, []).append(x)
    return out


def fingerprint(it):
    import hashlib
    keep = {k: it.get(k) for k in ("category", "ai_category", "decision", "recommended_option", "ai_recommendation", "proposed_code",
                                   "escalated", "check_verdict")}
    keep["s"] = (it.get("source") or {}).get("lines")
    keep["t"] = (it.get("target") or {}).get("lines")
    return hashlib.sha1(json.dumps(keep, sort_keys=True, default=str).encode()).hexdigest()[:12]


def render_state(folder, items):
    """Compare card fingerprints with the previous render. Re-rendering unchanged data keeps the earlier comparison."""
    p = os.path.join(folder, "render-state.json")
    fps = {i["id"]: fingerprint(i) for i in items}
    now = datetime.datetime.now().isoformat(timespec="seconds")
    try:
        st = json.load(open(p))
    except (OSError, json.JSONDecodeError):
        st = {}
    cur = st.get("current") or {}
    if cur.get("fp") != fps:
        st = {"previous": cur if cur.get("fp") else {}, "current": {"at": now, "fp": fps}}
        try:
            with open(p, "w") as f:
                json.dump(st, f, indent=1)
        except OSError:
            pass
    prev = (st.get("previous") or {}).get("fp") or {}
    if prev:
        STATE.update({"since": st["previous"].get("at"), "new": {k for k in fps if k not in prev},
                      "changed": {k for k in fps if k in prev and prev[k] != fps[k]}})
    return fps


def history_chips(it):
    out = []
    h = HIST.get(it.get("target_path") or it["file"]) or []
    if h:
        out.append(f'<a class="qchip hist" href="#history" title="{esc("; ".join(x["id"] + " (" + str(x["n"]) + " items)" for x in h))}">'
                   f'⟲ needed a person in {len(h)} earlier merge{"s" if len(h) > 1 else ""}</a>')
    if it["id"] in STATE.get("new", ()):
        out.append(f'<span class="qchip new" title="Not in the report rendered {esc(STATE.get("since"))}">new since last render</span>')
    elif it["id"] in STATE.get("changed", ()):
        out.append(f'<span class="qchip new" title="Code, AI review or decision differs from the report rendered {esc(STATE.get("since"))}">changed since last render</span>')
    return "".join(out)


COND = re.compile(r"^\s*(?:\}\s*else\s+)?(?:if|guard|while)\s+(.+?)\s*(?:else\s*)?\{?\s*$")


def checklist_for(it):
    """Behaviour checks a tester can tick on a device, generated from the change itself."""
    cat = it.get("ai_category") or it["category"]
    q = (QUAL.get("items") or {}).get(it["id"]) or {}
    out = []
    for sent in re.split(r"(?<=[.!?])\s+", it.get("ai_recommendation") or ""):
        m = re.search(r"business rule[:\s-]+(.+)", sent, re.I)
        if m:
            out.append("Rule holds: " + m.group(1).strip().rstrip("."))
    conds = []
    for side in ("source", "target"):
        snip = it.get(side) or {}
        for i in snip.get("marked") or []:
            line = (snip.get("lines") or [""] * (i + 1))[i] if i < len(snip.get("lines") or []) else ""
            m = COND.match(line)
            if m and len(m.group(1)) < 140:
                c = m.group(1).strip()
                if c not in conds:
                    conds.append(c)
    for c in conds[:3]:
        out.append(f"Exercise both outcomes of `{c}`")
    fns = q.get("functions") or []
    if fns and q.get("callers_total"):
        out.append(f"Flows that reach {', '.join(fns[:2])}() still work ({q['callers_total']} call sites)")
    plats = q.get("platform") or []
    if any("tvOS" in p for p in plats):
        out.append("Check on Apple TV (tvOS)")
    elif any("iOS" in p for p in plats):
        out.append("Check on iPhone / iPad (iOS)")
    if (it.get("decision") or it.get("recommended_option")) == "TARGET" and cat not in ("CLEAN", "ALREADY_PRESENT", "COSMETIC"):
        out.append("Confirm the dropped source behaviour is really not needed")
    if not out and it.get("ai_recommendation"):
        out.append("Behaviour matches: " + re.split(r"(?<=[.!?])\s", it["ai_recommendation"].strip())[0][:160])
    return list(dict.fromkeys(out))[:6]


def aids_html(it):
    q = (QUAL.get("items") or {}).get(it["id"]) or {}
    h = ""
    checks = checklist_for(it)
    if checks:
        h += (f'<div class="qa" data-id="{esc(it["id"])}"><b>Behaviour checklist</b> <span class="muted">(tick on a device; saved in this browser and in Export)</span><ul>'
              + "".join(f'<li><label><input type="checkbox" class="qak" data-k="{esc(it["id"])}:{n}"> <span>{esc(c)}</span></label></li>' for n, c in enumerate(checks))
              + "</ul></div>")
    calls = q.get("callers") or []
    if q.get("functions"):
        h += (f'<details class="calls"><summary>Who calls {esc(", ".join(f + "()" for f in q["functions"][:3]))} — {q.get("callers_total", 0)} call site{"" if q.get("callers_total") == 1 else "s"} in target</summary>'
              + ("<table class='list'>" + "".join(f'<tr><td><code>{esc(c["file"])}</code>:{c["line"]}</td><td><code>{esc(c["text"])}</code></td></tr>' for c in calls) + "</table>"
                 if calls else '<p class="muted">No call sites found by name (may be called through a protocol, selector or closure).</p>')
              + (f'<p class="muted">Showing {len(calls)} of {q["callers_total"]}.</p>' if q.get("callers_total", 0) > len(calls) else "") + "</details>")
    return h


def commit_data(items, s, t, rid, folder):
    rows = []
    for i in items:
        cat = i.get("ai_category") or i["category"]
        if cat in ("ALREADY_PRESENT", "COSMETIC", "IB_METADATA"):
            continue
        rows.append({"id": i["id"], "file": i.get("final_path") or i.get("target_path") or i["file"], "cat": cat,
                     "by": i.get("decided_by") or "", "dec": i.get("decision") or "",
                     "who": [f'{a.get("name")} {(a.get("date") or "")[:10]}'.strip() for a in (i.get("source_authors") or [])[:2]] or ["unknown"],
                     "sym": i.get("source_symbol") if i.get("source_symbol") and not str(i.get("source_symbol")).startswith("(") else ""})
    return {"src": s["branch"], "tgt": t["branch"], "rid": rid, "folder": folder, "rows": rows}


def history_section(d):
    if not HIST:
        return (f'<h2 id="history">Across merges</h2><p class="muted">No earlier merge report for <code>{esc(repo_key(d))}</code> in '
                '<code>~/Downloads/merge-reports</code>, so there are no hotspots yet. <a href="../index.html">All merge reports →</a></p>')
    rows = "".join(
        f'<tr><td><code>{esc(f)}</code></td><td><b>{len(h)}</b></td><td>' + "<br>".join(
            f'<a href="../{esc(x["id"])}/report.html">{esc(x["id"])}</a> <span class="muted">{esc(x["at"])} · {esc(x["branch"])} · {x["n"]} items · {esc(", ".join(x["cats"]))}</span>' for x in h)
        + "</td></tr>" for f, h in sorted(HIST.items(), key=lambda kv: -len(kv[1])))
    return ('<h2 id="history">Across merges — hotspots</h2><p class="muted">Files of this merge that needed a person in earlier merge reports of the same repository. '
            'A file that conflicts merge after merge is a sign two branches keep changing the same code — worth a refactor or an owner. '
            '<a href="../index.html">All merge reports →</a></p><table class="list"><tr><th>File</th><th>Earlier merges</th><th>Reports</th></tr>' + rows + "</table>")


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
    nf = sum(1 for r in trows if r[0] == 0)
    h += (f'<details><summary>Test impact — {nf} items whose function a test calls, {len(trows) - nt - nf} only by type name, {nt} with none ({QUAL.get("test_files", 0)} test files scanned)</summary>'
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
    global SRC_BRANCH, TGT_BRANCH
    setup_commit_links(d)
    SRC_BRANCH, TGT_BRANCH = d["source"]["branch"], d["target"]["branch"]
    vj = None
    try:
        vj = json.load(open(os.path.join(folder, "verification.json")))
        VERIFY.update({r["id"]: r for r in vj.get("results") or [] if r.get("id")})
    except (OSError, json.JSONDecodeError, AttributeError):
        vj = None
    build_j = None
    try:
        build_j = json.load(open(os.path.join(folder, "build-summary.json")))
    except (OSError, json.JSONDecodeError):
        build_j = None
    mine = {i.get("target_path") or i["file"] for i in d["items"]}
    HIST.update({f: h for f, h in history_scan(folder, d).items() if f in mine})
    FPS.update(render_state(folder, d["items"]))
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
            f'<b>{esc(x["code"])}</b> — {link_shas(esc(x["message"]))}'
            + ("".join(f' <a href="#{esc(i)}" class="dep">{esc(i)}</a>' for i in (x.get("items") or [])[:12]))
            + (f' <label class="confirm"><input type="checkbox" class="rack" data-ack="{esc(x["code"])}-{n}"> acknowledged / handled</label>' if x["level"] == "block" else "")
            + "</li>" for n, x in enumerate(sorted(rr, key=lambda x: order.get(x["level"], 9))))
        repo_risks_html = (f'<div id="repo-risks"><h3 style="margin:4px 0">Repository risks ({len(rr)})</h3><p class="muted" style="margin:2px 0">'
                           'Found by risk_scan.py across the whole repository. “Needs action” items block the merge until a person ticks them.</p><ul>' + lis + '</ul></div>')
    tiles = "".join(f'<div class="tile"><div class="n">{n}</div>{badge(c)}<div class="muted" style="font-size:12px">{esc(CAT_INFO.get(c, ("", ""))[1])}</div></div>'
                    for c, n in sorted(d["summary"]["by_category"].items(), key=lambda kv: -kv[1]))
    def who(lst, side="source"):
        return "".join(f'<div><b>{esc(p.get("name"))}</b> <span class="lines">{esc(ranges(p.get("line_numbers")) or "base " + ranges(p.get("base_line_numbers")))}</span> '
                       f'<span class="muted">{esc(p.get("role", ""))} · {esc((p.get("date") or "")[:10])} · </span>{clink(p.get("short"), p.get("sha"), side)}'
                       + (f'<div class="muted">↳ originally {esc(p["ported_from"]["name"])} ({clink(p["ported_from"]["short"], p["ported_from"].get("sha"), side)})</div>' if p.get("ported_from") else "")
                       + '</div>' for p in lst) or '<span class="muted">—</span>'
    talk = "".join(f'<tr><td><a href="#{esc(i["id"])}">{esc(i["id"])}</a></td><td>{badge(i.get("ai_category") or i["category"])}</td>'
                   f'<td><code>{esc(i.get("target_path") or i["file"])}</code></td><td>{who(i.get("source_authors", []), "source")}</td>'
                   f'<td>{who(i.get("target_authors", []), "target")}</td></tr>' for i in need_all)
    owners = {}
    for i in need_all:
        for side, key in (("incoming", "source_authors"), ("current", "target_authors")):
            for p in i.get(key, []):
                o = owners.setdefault(p.get("name"), {"email": p.get("email"), "ids": []})
                o["ids"].append(f'{i["id"]} ({side})')
    devs = "".join(f'<tr><td><b>{esc(n)}</b></td><td>{esc(v["email"])}</td><td>{esc(", ".join(dict.fromkeys(v["ids"])))}</td></tr>'
                   for n, v in sorted(owners.items(), key=lambda kv: -len(kv[1]["ids"])))
    commits = "".join(f'<tr><td>{clink(c["short"], c.get("sha"), "source")}</td><td>{esc(c["date"])}</td><td>{esc(c["name"])}</td><td>{esc(c["subject"])}</td>'
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

    quality_html = quality_section(d, items) + history_section(d)
    start = {"verify": None, "build": None, "lint": None, "risk_high": None, "missing": [], "rewritten": []}
    if vj:
        start["verify"] = {"ok": bool(vj.get("ok")), "missing": vj.get("missing_items") or 0, "still": vj.get("still_present_items") or 0}
        start["missing"] = [r["id"] for r in vj.get("results") or [] if r.get("missing")]
        start["rewritten"] = [r["id"] for r in vj.get("results") or [] if str(r.get("status", "")).startswith("CHECK")]
    if build_j and build_j.get("results"):
        res = build_j["results"]
        start["build"] = {"ok": bool(build_j.get("all_succeeded")), "n": len(res), "passed": sum(1 for r in res if r.get("status") == "SUCCEEDED"),
                          "failed": [r["scheme"] for r in res if r.get("status") != "SUCCEEDED"], "at": build_j.get("finished")}
    if QUAL:
        lt = QUAL.get("lint") or {}
        if lt.get("status") == "ok":
            start["lint"] = {"new": lt.get("new_total", 0), "merged": lt.get("on_merged_lines", 0)}
        start["risk_high"] = sum(1 for f in (QUAL.get("files") or {}).values() if f.get("level") == "high")
        start["unresolved"] = [m["module"] for m in QUAL.get("build_missing_modules") or []]
    start_js = "const START_DATA=" + json.dumps(start).replace("</", "<\\/") + ";"
    shalinks = {}
    for sha_, side_ in KNOWN_SHAS.items():
        u_ = commit_url(sha_, side_)
        if u_:
            shalinks[sha_] = u_
    commit_js = "const SHA_LINKS=" + json.dumps(shalinks) + ";const COMMIT_DATA=" + json.dumps(commit_data(items, s, t, rid, folder)).replace("</", "<\\/") + ";"
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
    ai_cmd = f'python3 "{os.path.join(os.path.dirname(os.path.abspath(__file__)), "report_server.py")}" "{folder}" --open'
    page = f'''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Merge report {esc(s["branch"])} → {esc(t["branch"])} · {esc(rid)}</title><style>{CSS}{TRACKER_CSS}{EXTRA_CSS}{EXTRA3_CSS}{EXTRA4_CSS}{EXTRA5_CSS}{EXTRA6_CSS}{EXTRA7_CSS}{EXTRA8_CSS}{EXTRA9_CSS}</style></head><body>
<div class="bar"><div class="brow">
<a class="rid" href="#start" title="{esc(rid)}">{esc(s["branch"])} → {esc(t["branch"])}</a><span id="rready" class="chip"></span><span id="rstat" class="chip"></span>
<span class="grow"></span>
<input id="q" type="search" placeholder="Search ( / )" title="Search card IDs, files, functions, authors and code"><span id="qcount"></span>
<button class="sec" onclick="nextPending()" title="Jump to the next card nobody reviewed yet (n)" aria-label="Next pending card"><span class="lg">Next pending </span>▶</button>
<details class="menu" id="fmenu"><summary class="btn sec">Filters<span id="fcount"></span> ▾</summary><div class="pop">
<label>Status<select id="rfilter"><option value="all">All cards</option><option value="pend">Pending review</option><option value="done">Reviewed</option><option value="conf">Reviewers disagree</option></select></label>
<label>Developer<select id="rdev"><option value="">Everyone</option></select></label>
<label>Risk<select id="rrisk"><option value="">Any</option>{"".join(f'<option value="{k}">{esc(v)}</option>' for k, v in {**RISK_LABELS, **QUAL_LABELS}.items())}</select></label>
<label>Area<select id="rarea"><option value="">All areas</option>{"".join(f'<option value="{esc(a)}">{esc(a)}</option>' for a in areas)}</select></label>
<label>Assigned<select id="rassign"><option value="">Anyone</option><option value="me">Me</option><option value="any">Someone</option><option value="none">Nobody</option></select></label>
<button class="sec" type="button" onclick="clearFilters()">Clear filters</button></div></details>
<input id="by" readonly placeholder="Reviewer?" title="Reviewer — saved with every decision" aria-label="Reviewer">
<button onclick="exportJson()" title="Download your decisions as a JSON file for the merge owner" aria-label="Export decisions">Export<span class="lg"> decisions</span></button>
<details class="menu right" id="mmenu"><summary class="btn sec" title="More options">⋯</summary><div class="pop mpop">
<label class="mname">Reviewer<input id="by2" readonly placeholder="Not set" aria-label="Reviewer"></label>
<div class="ph">Save &amp; share</div>
<div id="rsave"></div>
<button class="mi" type="button" onclick="document.getElementById('importf').click()"><span class="mic">⤓</span>Import decisions (.json)…</button><input type="file" id="importf" accept=".json,application/json" multiple style="display:none">
<button class="mi" type="button" onclick="showPendingList()"><span class="mic">⧉</span>Copy pending list for Slack</button>
<div class="ph">View</div>
<div class="segrow"><span>Diff</span><div class="seg" data-k="diff"><button type="button" data-val="0">Side by side</button><button type="button" data-val="1">Inline</button></div></div>
<div class="segrow"><span>Base column</span><div class="seg" data-k="base"><button type="button" data-val="0">Show</button><button type="button" data-val="1">Hide</button></div></div>
<div class="segrow"><span>Theme</span><div class="seg" data-k="theme"><button type="button" data-val="auto">Auto</button><button type="button" data-val="light">Light</button><button type="button" data-val="dark">Dark</button></div></div>
<div class="segrow"><span>Cards</span><div class="seg plain"><button type="button" onclick="expandAll(true)">Expand all</button><button type="button" onclick="expandAll(false)">Collapse all</button></div></div>
<div class="ph">AI help</div>
<button class="mi ai-on-only" type="button" onclick="document.getElementById('mmenu').open=false;openAI()"><span class="mic">✦</span>Ask AI about this merge<kbd style="margin-left:auto">q</kbd></button>
<button class="mi ai-off-only" type="button" onclick="document.getElementById('mmenu').open=false;showAiHint()" title="Ask the Cursor agent about any conflict — needs the report helper and a Cursor login"><span class="mic">✦</span>Turn on AI help…</button>
<div class="ph">More</div>
<button class="mi" type="button" onclick="window.print()"><span class="mic">⎙</span>Print / PDF</button>
<button class="mi" type="button" onclick="toggleHelp()"><span class="mic">⌨</span>Keyboard shortcuts<kbd style="margin-left:auto">?</kbd></button>
<span id="progress" hidden></span>
<div class="ph jump">Jump to</div><div class="jl jump" id="jumplinks"></div>
</div></details>
</div><div id="pbar"><i></i></div></div>
<nav id="toc" aria-label="Sections"></nav>
<div id="minimap" aria-label="Card map"></div>
<button id="aibub" type="button" onclick="openAI()" title="Ask the Cursor agent about this card or the whole merge (q)"><span>✦ Ask AI</span><span class="k" id="aibubacct">q</span></button>
<div id="aicall" hidden role="note"><b>New: ask AI about any conflict.</b><br>Click <b>✦ Ask AI</b> on a card, or here, or press <kbd>q</kbd>. The Cursor agent on your Mac reads the code (read-only) and explains.<br><button type="button" onclick="dismissCall()">Got it</button></div>
<section id="aipanel" hidden aria-label="Ask AI"><div class="aph"><b>✦ Ask AI</b><select id="aictx" title="What the question is about"></select><span class="grow"></span><button type="button" onclick="closeAI()" title="Close (Esc)">×</button></div>
<div class="apm" id="aimsgs"></div><div class="asug" id="aisug"></div>
<div class="aif"><textarea id="aiq" rows="1" placeholder="Ask about this conflict… (Enter to send)"></textarea><button id="aisend" type="button">Send</button></div>
<div class="afoot">Answers by your local Cursor agent in read-only mode — it never edits code. Uses your Cursor account. Check answers before you decide.</div></section>
<dialog id="whodlg" aria-labelledby="whot"><b id="whot" style="font-size:17px">Who is reviewing?</b>
<p class="muted" style="margin:6px 0 10px">Your name is saved with every decision, note and tick you make in this report, so the team knows who reviewed what. Once set, it can't be changed in this browser.</p>
<label style="display:flex;flex-direction:column;gap:4px;font-weight:600;font-size:13px">Your full name<input id="whoname" required minlength="2" maxlength="80" autocomplete="name" placeholder="e.g. Rakesh Sharma" style="font-size:16px;padding:8px 10px;border:1px solid #cfd8dc;border-radius:8px"></label>
<p class="muted" style="font-size:12px;margin:8px 0 0">Tip: open the report with <code>report_server.py</code> and your name is taken from <code>git config user.name</code> automatically.</p>
<div class="row" style="display:flex;justify-content:space-between;gap:8px;margin-top:14px;align-items:center"><a href="#" id="whobrowse" style="font-size:13px">Just look around (read-only)</a><button type="button" id="whook" disabled>Start reviewing</button></div></dialog>
<dialog id="aihint"><b style="font-size:16px">✦ Turn on AI help</b><p id="aihintwhy" class="muted"></p>
<p>Ask the Cursor agent about any card — why the sides differ, what breaks, which option is safest — right in this report.</p><ol>
<li>Log in once: <code>cursor-agent login</code> <span class="muted">(check with <code>cursor-agent status</code>)</span></li>
<li>Open the report through the helper: <code>{esc(ai_cmd)}</code> <button type="button" onclick="copyText(this.previousElementSibling.textContent,'Command')" style="padding:2px 8px">Copy</button></li>
<li>An <b>✦ Ask AI</b> bubble appears at the bottom right and on every card.</li></ol>
<p class="muted" style="font-size:12px">The helper only listens on this Mac. The agent runs in read-only ask mode in <code>{esc(d["target"].get("repo_root") or d["target"]["folder"])}</code>; questions use your Cursor account.</p>
<div class="row"><button type="button" onclick="this.closest('dialog').close()">Close</button></div></dialog>
<div id="khelp" hidden><b>Keyboard</b><table>
<tr><td><kbd>j</kbd> / <kbd>k</kbd></td><td>next / previous card</td></tr><tr><td><kbd>n</kbd></td><td>next pending card</td></tr>
<tr><td><kbd>s</kbd> <kbd>t</kbd> <kbd>b</kbd> <kbd>a</kbd> <kbd>c</kbd></td><td>use incoming / keep current / keep both / AI's version / custom</td></tr>
<tr><td><kbd>Enter</kbd></td><td>accept the AI suggestion (★)</td></tr><tr><td><kbd>o</kbd></td><td>show / hide the card's details</td></tr><tr><td><kbd>r</kbd></td><td>toggle “Mark reviewed”</td></tr>
<tr><td><kbd>e</kbd></td><td>write notes (Esc to leave)</td></tr><tr><td><kbd>l</kbd></td><td>copy a link to the card</td></tr>
<tr><td><kbd>g</kbd></td><td>jump to the first evidence line</td></tr><tr><td><kbd>/</kbd></td><td>search cards</td></tr><tr><td><kbd>m</kbd></td><td>assign the card to me</td></tr><tr><td><kbd>i</kbd></td><td>inline / 3-way diff</td></tr><tr><td><kbd>q</kbd></td><td>ask AI about the current card (when AI help is on)</td></tr><tr><td><kbd>d</kbd></td><td>toggle dark mode</td></tr><tr><td><kbd>?</kbd></td><td>this help</td></tr></table></div>
<div class="wrap">
<h1 id="top">Merge <code>{esc(s["branch"])}</code> → <code>{esc(t["branch"])}</code></h1>
<div class="muted">{esc(d.get("status")).replace("_", " ").lower()} · generated {esc(d["generated_at"][:16].replace("T", " "))} · {d["summary"]["items"]} changes from {d["summary"]["source_commits"]} commits</div>
<section id="start" aria-live="polite"><div class="sh" id="starthead">…</div><ul id="startfacts"></ul><div id="startnext"></div></section>
{repo_risks_html}
<details class="aux"><summary>Report details &amp; how to use this page</summary>
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

<h3>How to read a card</h3><ul>
<li>Each card is collapsed to the essentials: <b>what the AI suggests</b>, status chips and your options. <b>Show details</b> (or <kbd>o</kbd>) opens the code, evidence and checks.</li>
<li><b>Base</b> — the code at the last commit both branches share (<code>{esc((d["analysis_base"] or "")[:12])}</code>). Red = what was there and got changed.</li>
<li><b>Incoming</b> — the same code on <code>{esc(s["branch"])}</code> (what the merge brings). Green = changed there.</li>
<li><b>Current</b> — the same code on <code>{esc(t["branch"])}</code> (what you have). Amber = changed there.</li>
<li>The purple name next to a line is the developer who wrote that exact line (on Base: who removed it).</li>
<li><b>Options:</b> “Use incoming change” replaces the current code — if current was refactored, those improvements are lost. To keep the incoming fix <i>and</i> current's design, pick “Use AI's merged version”.</li>
<li><b>AI help:</b> open the report with <code>report_server.py</code> while logged in to the Cursor agent, and a <b>✦ Ask AI</b> bubble (bottom right) and button on every card let you ask about any conflict. ⋯ → <i>Turn on AI help…</i> shows how.</li>
<li><b>Colours:</b> <span class="qchip block">red</span> blocks the merge · <span class="qchip look">amber</span> needs a look · <span class="qchip ok">green</span> done / fine · <span class="qchip">grey</span> information.</li></ul>
{structure_html}
</details>
<details class="aux"><summary>Numbers &amp; people</summary>
<h2 style="margin-top:8px">Summary</h2>
<div class="tiles"><div class="tile"><div class="n">{d["summary"]["needs_decision"]}</div>decisions needed</div>
<div class="tile"><div class="n">{d["summary"]["items"]}</div>change items</div><div class="tile"><div class="n">{d["summary"]["source_commits"]}</div>source commits</div>
<div class="tile"><div class="n">{d["summary"]["files_changed_in_source"]}</div>files changed in source</div>{tiles}</div>
{"<p class='warn'><b>Warning:</b> AI review missing for " + ", ".join(missing_ai) + "</p>" if missing_ai else ""}
<h3>Who to talk to — exact authors of the conflicting lines</h3>
<p class="muted">Only the developers who wrote (or removed) the exact lines in each decision item — taken line by line from git blame, not from who else touched the file.</p>
<table class="list"><tr><th>Item</th><th>Type</th><th>File</th><th>Incoming lines written by</th><th>Current lines written by</th></tr>{talk or '<tr><td colspan="5">No decisions needed.</td></tr>'}</table>
<h3>Per developer</h3><table class="list"><tr><th>Developer</th><th>Email</th><th>Decision items (side)</th></tr>{devs or '<tr><td colspan="3">—</td></tr>'}</table>
</details>

<div id="idnote">👤 <b>Set your name to review.</b> Decisions, notes and ticks are saved with the reviewer's name. <a href="#" onclick="askWho();return false">Set reviewer…</a></div>
<div id="seenbar" hidden><b></b><button class="cpbtn" type="button" id="onlynew" onclick="onlyNew()">Show only these</button><button class="cpbtn alt" type="button" onclick="markAllSeen()">Mark all seen</button></div>
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
{quality_html}
<div id="areas"></div>
<h2 id="qa">QA test plan</h2><p class="muted">Every card's behaviour checklist, grouped by feature area. Generated from the change (business rules in the AI recommendation, changed <code>if</code>/<code>guard</code> conditions, callers, platform). Ticks are saved in this browser and in Export / auto-save.</p><div id="qaplan"></div>
<h2 id="commit">Commit message preview</h2><p class="muted">Follows your current choices live. The file the developer commits with is still written by <code>commit_message.py</code> (it also adds the merged line numbers and build results). <button class="cpbtn" type="button" onclick="copyText(commitText(),'Commit message')">Copy</button></p><pre id="commitprev"></pre>
<h2 id="paths">File / path map ({len(d["files"])})</h2><details><summary>Show</summary><table class="list"><tr><th>Source path</th><th>Status</th><th>Target path</th><th>Method</th><th>Confidence</th><th>Protected</th></tr>{paths}</table></details>
<h2 id="commits">Source commits ({len(d["commits"])})</h2><details><summary>Show</summary><table class="list"><tr><th>Commit</th><th>Date</th><th>Author</th><th>Subject</th><th></th></tr>{commits}</table></details>
<h2>Changed only in target ({len(d.get("target_only_changes", []))})</h2><details><summary>Show</summary><p class="muted">Not touched by the merge; listed for context.</p><table class="list">{tgt_only}</table></details>
<p class="muted" style="margin-top:30px">Generated by the safe-branch-merge skill · {esc(rid)}</p>
</div><script>{JS % {"rid": json.dumps(rid)}}{meta_js}{commit_js}{start_js}{TRACKER_JS}{EXTRA_JS}{EXTRA3_JS}{EXTRA4_JS}{EXTRA5_JS}{EXTRA6_JS}{EXTRA7_JS}{EXTRA8_JS}{EXTRA9_JS}</script></body></html>'''
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
                cu = commit_url(p.get("sha") or p.get("short"), side)
                cid = f"[`{p.get('short')}`]({cu})" if cu else f"`{p.get('short')}`"
                out.append(f"- {label}: **{p.get('name')}** <{p.get('email')}> — {p.get('role', '')}{ln} — {p.get('date')} — {cid} {p.get('subject')}{port}")
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
        cu = commit_url(c.get("sha") or c["short"], "source")
        md.append(f"- {('[`' + c['short'] + '`](' + cu + ')') if cu else ('`' + c['short'] + '`')} {c['date']} **{c['name']}** — {c['subject']}" + (" *(equivalent already in target)*" if c.get("already_in_target") else ""))
    with open(os.path.join(folder, "report.md"), "w") as f:
        f.write("\n".join(md) + "\n")

    print(f"written: {os.path.join(folder, 'report.html')}")
    print(f"written: {os.path.join(folder, 'report.md')}")
    try:                                                   # refresh ../index.html (all merge reports)
        import importlib.util
        spec = importlib.util.spec_from_file_location("render_index", os.path.join(os.path.dirname(os.path.abspath(__file__)), "render_index.py"))
        ri = importlib.util.module_from_spec(spec); spec.loader.exec_module(ri)
        sys_argv, sys.argv = sys.argv, ["render_index.py", os.path.dirname(folder)]
        try:
            ri.main()
        finally:
            sys.argv = sys_argv
    except Exception as e:                                 # the index is a convenience; never fail the report for it
        print(f"note: index.html not updated ({e})")
    print(f"needs developer: {len(need)}  decided by AI: {len(ai_decided)}  by developer: {len(dev_decided)}  review: {len(review)}  auto: {len(auto)}")
    if missing_ai:
        print("WARNING: AI analysis/recommendation missing for: " + ", ".join(missing_ai))
        sys.exit(3)


if __name__ == "__main__":
    main()
