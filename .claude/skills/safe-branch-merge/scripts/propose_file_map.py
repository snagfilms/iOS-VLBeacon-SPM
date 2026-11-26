#!/usr/bin/env python3
"""
propose_file_map.py — draft the FILE MAP for a restructured merge, for the AI agent to review and finish.

For every source file that changed and is NOT at the same path in target (moved, split, missing, uncertain, new):
  * each changed function/type is looked up in the target branch by name + signature (symbols.py)
    → which target file defines it now;
  * if names changed, distinctive lines of the old code (calls, string literals) are searched in target;
  * files whose changed functions now live in several target files → status "split" (per-function targets);
  * files only in source → "new": proposed folder (folder map, imports, types it uses, sibling modules)
    and proposed build membership: Xcode targets (from files already in that folder) / SPM target (Package.swift).

Usage:
  propose_file_map.py <report>/analysis.json [--out <report>/file-map.draft.json] [--all]
    --all  also include files at the same path (normally skipped)

Output schema "file-map/1" (the AI edits it and saves it as <report>/file-map.json, then re-runs collect_changes.py
with --map-file <report>/file-map.json):
{
  "schema": "file-map/1", "report_id": "...",
  "folders": { "Old/Folder/": "New/Folder/" | null },
  "files": {
    "<source path>": {
      "status": "mapped | split | new | not-in-target | unknown",
      "target": "<target path>" | null,                    # mapped / split (primary file)
      "symbols": { "<Type.func(label:)>": {"target": "<file>", "target_symbol": "...", "evidence": "..."} },   # split
      "placement": { "path": "...", "why": "...", "xcode_targets": [...], "spm_target": "..." },             # new
      "confidence": 0.0-1.0, "evidence": [ ... ], "candidates": [ ... ],
      "decided_by": "script-draft | ai | developer", "needs_developer": true|false, "note": "AI reasoning"
    }
  }
}
"""
import argparse, json, os, re, subprocess, sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import symbols as SYM  # noqa: E402

STD_IMPORTS = {"Foundation", "UIKit", "SwiftUI", "Combine", "AVFoundation", "AVKit", "CoreData", "CoreGraphics", "os",
               "Darwin", "Dispatch", "UserNotifications", "XCTest", "TVUIKit", "WebKit", "StoreKit", "Network", "CoreMedia",
               "QuartzCore", "MediaPlayer", "AppTrackingTransparency", "AdSupport", "Security", "SystemConfiguration"}


def git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True)
    return r.returncode, r.stdout.decode("utf-8", errors="replace")


_cache = {}
def show(repo, ref, path):
    k = (ref, path)
    if k not in _cache:
        rc, out = git(repo, "show", f"{ref}:{path}")
        _cache[k] = out if rc == 0 and "\0" not in out[:4000] else None
    return _cache[k]


def norm(s):
    return re.sub(r"\s+", " ", s.strip())


HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
def hunks(repo, a, b):
    rc, out = git(repo, "diff", "-U0", "--no-color", "--diff-algorithm=histogram", a, b)
    res = []
    for line in out.splitlines():
        m = HUNK_RE.match(line)
        if m:
            x, xc, y, yc = int(m.group(1)), m.group(2), int(m.group(3)), m.group(4)
            xc = 1 if xc is None else int(xc); yc = 1 if yc is None else int(yc)
            bs = x if xc == 0 else x - 1; ts = y if yc == 0 else y - 1
            res.append({"bs": bs, "be": bs + xc, "ts": ts, "te": ts + yc})
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("analysis")
    ap.add_argument("--out")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    d = json.load(open(a.analysis))
    folder = os.path.dirname(os.path.abspath(a.analysis))
    repo, base, sref, tref = d["target"]["repo_root"], d["analysis_base"], d["source"]["ref"], d["target"]["ref"]
    rc, tree = git(repo, "ls-tree", "-r", "--name-only", tref)
    ttree = tree.split("\n")
    tset = set(ttree)
    tdirs = Counter(os.path.dirname(p) for p in ttree)

    idx_cache = {}
    def sidx(ref, path):
        if (ref, path) not in idx_cache:
            t = show(repo, ref, path)
            idx_cache[(ref, path)] = (t or "", SYM.index(t or "", SYM.lang_of(path)))
        return idx_cache[(ref, path)]

    def find_symbol(sym, lang):
        name = re.escape(sym.name)
        pat = {"objc": rf"[-+]\s*\([^)]*\)\s*{name}\b|@(interface|implementation)\s+{name}\b"}.get(
            lang, rf"\b(func|fun|function|def|var|let|val|case|class|struct|enum|protocol|actor|interface|object|extension|type)\s+{name}\b")
        ext = {"swift": "*.swift", "objc": "*.m", "kotlin": "*.kt", "java": "*.java", "js": "*.[jt]s*", "csharp": "*.cs", "go": "*.go"}.get(lang, "*")
        rc, out = git(repo, "grep", "-l", "-E", pat, tref, "--", ext)
        hits = []
        for h in out.splitlines()[:40]:
            f = h.split(":", 1)[1] if ":" in h else h
            t, ix = sidx(tref, f)
            m = SYM.find(ix, sym)
            if m:
                hits.append((f, m.qual))
        return hits

    def distinctive_hits(lines):
        cand = sorted({l.strip() for l in lines if len(l.strip()) >= 22 and not l.strip().startswith(("//", "/*", "*", "import"))},
                      key=lambda x: (-("\"" in x), -len(x)))[:5]
        votes = Counter()
        for l in cand:
            rc, out = git(repo, "grep", "-l", "-F", l, tref, "--")
            fs = [h.split(":", 1)[1] for h in out.splitlines() if ":" in h]
            if 0 < len(fs) <= 5:
                for f in fs:
                    votes[f] += 1
        return votes, len(cand)

    # ---------- build-membership helpers (Xcode + SPM)
    pbx_files = [p for p in ttree if p.endswith("project.pbxproj") and "/Pods/" not in p]
    pbx_roots = {}
    def pbx_root(p):
        if p not in pbx_roots:
            try:
                import pbx_targets as PBX
                pbx_roots[p] = PBX.load(p, tref, repo)
            except Exception:
                pbx_roots[p] = None
        return pbx_roots[p]

    def xcode_targets_for_dir(dirpath):
        sibs = [p for p in ttree if os.path.dirname(p) == dirpath and SYM.lang_of(p)][:6]
        res = Counter()
        try:
            import pbx_targets as PBX
        except Exception:
            return []
        for pf in pbx_files:
            root = pbx_root(pf)
            if not root:
                continue
            for sname in sibs:
                for t, ph in PBX.memberships(root, os.path.basename(sname)).items():
                    if ph == "Sources":
                        res[t] += 1
        return [t for t, _ in res.most_common()]

    spm = []
    for p in ttree:
        if os.path.basename(p) == "Package.swift":
            txt = show(repo, tref, p) or ""
            pdir = os.path.dirname(p)
            for m in re.finditer(r"\.(target|executableTarget|testTarget|macro)\s*\(\s*name:\s*\"([^\"]+)\"", txt):
                kind, name = m.group(1), m.group(2)
                seg = txt[m.end(): m.end() + 1500]
                nxt = re.search(r"\.(?:target|executableTarget|testTarget|binaryTarget|macro)\s*\(", seg)
                seg = seg[: nxt.start()] if nxt else seg
                pm = re.search(r"path:\s*\"([^\"]+)\"", seg)
                tp = pm.group(1) if pm else (("Tests/" if kind == "testTarget" else "Sources/") + name)
                spm.append((os.path.normpath(os.path.join(pdir, tp)), name))

    def spm_target_for(path):
        best = None
        for tp, name in spm:
            if path == tp or path.startswith(tp + "/"):
                if best is None or len(tp) > len(best[0]):
                    best = (tp, name)
        return best[1] if best else None

    def placement_for(src_path, text, item):
        votes, why = Counter(), defaultdict(list)
        sugg = (item or {}).get("suggested_target_path")
        if sugg and os.path.dirname(sugg) in tdirs:
            votes[os.path.dirname(sugg)] += 3; why[os.path.dirname(sugg)].append("folder map / sibling files")
        for mod in re.findall(r"^\s*(?:@testable\s+)?import\s+(?:class\s+|struct\s+)?([A-Za-z_][\w.]*)", text or "", re.M):
            mod = mod.split(".")[0]
            if mod in STD_IMPORTS:
                continue
            rc, out = git(repo, "grep", "-l", "-E", rf"^\s*(@testable\s+)?import\s+{re.escape(mod)}\b", tref, "--")
            dirs = Counter(os.path.dirname(h.split(":", 1)[1]) for h in out.splitlines() if ":" in h)
            for dd, c in dirs.most_common(3):
                votes[dd] += 2; why[dd].append(f"other files importing {mod} live here")
        used = set(re.findall(r"\b([A-Z][A-Za-z0-9_]{3,})\b", text or "")) - set(re.findall(r"\b(?:class|struct|enum|protocol|actor)\s+([A-Z]\w+)", text or ""))
        for tname in list(used)[:25]:
            rc, out = git(repo, "grep", "-l", "-E", rf"\b(class|struct|enum|protocol|actor)\s+{tname}\b", tref, "--", "*.swift", "*.kt", "*.java", "*.m", "*.h")
            for h in out.splitlines()[:2]:
                dd = os.path.dirname(h.split(":", 1)[1])
                votes[dd] += 1; why[dd].append(f"uses {tname}")
        if not votes:
            return None
        best, score = votes.most_common(1)[0]
        path = f"{best}/{os.path.basename(src_path)}" if best else os.path.basename(src_path)
        return {"path": path, "why": "; ".join(dict.fromkeys(why[best]))[:300], "score": score,
                "alternatives": [{"dir": dd, "score": sc} for dd, sc in votes.most_common(4)[1:]],
                "xcode_targets": xcode_targets_for_dir(best), "spm_target": spm_target_for(path)}

    items_by_file = defaultdict(list)
    for it in d["items"]:
        items_by_file[it["file"]].append(it)

    out_files = {}
    for f in d["files"]:
        sp, bp, st, tp = f["source_path"], f["base_path"], f["source_status"], f["target_path"]
        cats = {i["category"] for i in items_by_file.get(sp, [])}
        same = tp in (sp, bp) and f["mapping"]["method"].startswith("same-path")
        if same and not a.all and not (cats & {"MAPPING_UNCERTAIN", "SYMBOL_NOT_FOUND"}):
            continue
        if f["kind"] == "bundle" or st == "bundle":
            out_files[sp] = {"status": "not-in-target" if not tp else "mapped", "target": tp, "confidence": 0.9,
                             "evidence": ["vendored bundle — see its VENDORED_BUNDLE card"], "decided_by": "script-draft",
                             "needs_developer": not tp, "note": ""}
            continue
        lang = SYM.lang_of(sp)
        entry = {"status": "unknown", "target": None, "symbols": {}, "confidence": 0.0, "evidence": [], "candidates": [],
                 "decided_by": "script-draft", "needs_developer": True, "note": "",
                 "script_mapping": {"method": f["mapping"]["method"], "confidence": f["mapping"]["confidence"],
                                    "guess": tp or next((i.get("guessed_target_path") for i in items_by_file.get(sp, []) if i.get("guessed_target_path")), None)}}
        if st == "A":
            it = next(iter(items_by_file.get(sp, [])), None)
            if tp and f["mapping"]["confidence"] >= 0.85:
                entry.update(status="mapped", target=tp, confidence=f["mapping"]["confidence"], needs_developer=False,
                             evidence=[f"same file already exists in target ({f['mapping']['method']})"])
            else:
                pl = placement_for(sp, show(repo, sref, sp), it)
                entry.update(status="new", placement=pl or {"path": None, "why": "no evidence — ask"},
                             confidence=min(0.95, 0.5 + 0.1 * pl["score"]) if pl else 0.2,
                             needs_developer=not pl or pl["score"] < 3,
                             evidence=[pl["why"]] if pl else ["no folder evidence"])
            out_files[sp] = entry
            continue
        if not lang:
            if tp and f["mapping"]["confidence"] >= 0.85:
                entry.update(status="mapped", target=tp, confidence=f["mapping"]["confidence"], needs_developer=False,
                             evidence=[f["mapping"]["method"]])
            out_files[sp] = entry
            continue
        btxt, bidx = sidx(base, bp)
        stxt, sidx_ = sidx(sref, sp) if st != "D" else ("", [])
        hs = hunks(repo, f"{base}:{bp}", f"{sref}:{sp}") if st != "D" else []
        changed = {}
        for h in hs:     # every changed line belongs to its own innermost function (one hunk can touch several)
            for ln in range(h["ts"], h["te"]):
                ref = SYM.enclosing(sidx_, ln)
                if ref:
                    changed.setdefault(ref.qual, (ref, SYM.find(bidx, ref) is not None))
            for ln in range(h["bs"], h["be"]):
                ref = SYM.enclosing(bidx, ln)
                if ref:
                    changed.setdefault(ref.qual, (ref, True))
        # a type is listed only if no function inside it was found for the same change
        quals = list(changed)
        for q in quals:
            ref, _ = changed[q]
            if ref.kind == "type" and any(q2.startswith(ref.name + ".") for q2 in quals if q2 != q):
                changed.pop(q)
        if st == "D":
            for s_ in bidx:
                if s_.kind == "func":
                    changed.setdefault(s_.qual, (s_, True))
        file_votes = Counter()
        for qual, (ref, in_base) in changed.items():
            hits = find_symbol(ref, lang)
            if len(hits) == 1:
                entry["symbols"][qual] = {"target": hits[0][0], "target_symbol": hits[0][1], "evidence": "same name + signature"}
                file_votes[hits[0][0]] += 2
                continue
            if len(hits) > 1:
                pref = [h for h in hits if h[0] == tp] or hits
                entry["symbols"][qual] = {"target": pref[0][0], "target_symbol": pref[0][1],
                                          "evidence": "defined in several files: " + ", ".join(h[0] for h in hits[:4]), "ambiguous": len(pref) > 1}
                file_votes[pref[0][0]] += 1
                continue
            body = SYM.body(btxt if in_base else stxt, SYM.find(bidx, ref) or ref) if (in_base and SYM.find(bidx, ref)) else []
            votes, n = distinctive_hits(body)
            if votes:
                bf, c = votes.most_common(1)[0]
                entry["symbols"][qual] = {"target": bf, "target_symbol": None,
                                          "evidence": f"{c}/{n} distinctive lines of the old code found there (renamed/rewritten?)"}
                file_votes[bf] += 1
            elif not in_base:
                entry["symbols"][qual] = {"target": None, "target_symbol": None, "evidence": "new in source — goes next to its type",
                                          "container": ref.container}
            else:
                entry["symbols"][qual] = {"target": None, "target_symbol": None, "evidence": "not found in target (removed? renamed?)"}
        # new symbols follow their container type
        for qual, e in entry["symbols"].items():
            if e["target"] is None and e.get("container"):
                # prefer the file that DECLARES the type (not an extension), then files where its other functions went
                rc, outc = git(repo, "grep", "-l", "-E", rf"^\s*(\w+\s+)*(class|struct|enum|actor|protocol)\s+{re.escape(e['container'])}\b", tref, "--")
                homes = [h.split(":", 1)[1] for h in outc.splitlines() if ":" in h][:1]
                if not homes:
                    homes = [x["target"] for q2, x in entry["symbols"].items() if x["target"] and q2.startswith(e["container"] + ".")]
                if homes:
                    e["target"] = Counter(homes).most_common(1)[0][0]
                    e["evidence"] += f" → {e['target']}"
        targets = Counter(e["target"] for e in entry["symbols"].values() if e["target"])
        found = sum(1 for e in entry["symbols"].values() if e["target"])
        total = max(1, len(entry["symbols"]))
        if not targets:
            if tp and f["mapping"]["confidence"] >= 0.85:
                entry.update(status="mapped", target=tp, confidence=f["mapping"]["confidence"], needs_developer=False,
                             evidence=[f"script mapping {f['mapping']['method']}"])
            else:
                entry.update(status="unknown", evidence=["no changed function found in target"], needs_developer=True)
        elif len(targets) == 1:
            t1 = next(iter(targets))
            conf = round(0.6 + 0.35 * found / total + (0.05 if t1 == tp else 0), 2)
            entry.update(status="mapped", target=t1, confidence=min(conf, 0.98), needs_developer=conf < 0.8,
                         evidence=[f"{found}/{total} changed functions/types are in {t1}"])
            if found == total:
                entry["symbols"] = {}   # simple mapping, no per-function table needed
        else:
            prim = sorted(targets.items(), key=lambda kv: (kv[1], kv[0] == tp), reverse=True)[0][0]
            conf = round(0.55 + 0.35 * found / total, 2)
            entry.update(status="split", target=prim, confidence=conf, needs_developer=conf < 0.8 or any(e.get("ambiguous") for e in entry["symbols"].values()),
                         evidence=[f"changed functions now live in {len(targets)} files: " + ", ".join(f"{t} ({c})" for t, c in targets.most_common())])
        entry["candidates"] = [t for t, _ in file_votes.most_common(5)]
        out_files[sp] = entry

    folders = {}
    for v in (d.get("structure") or {}).get("folder_map", []):
        folders[(v["source_dir"] or "") + "/"] = (v["target_dir"] + "/") if v["target_dir"] else None
    res = {"schema": "file-map/1", "report_id": d["report_id"], "generated_by": "propose_file_map.py — DRAFT, the AI must review every entry",
           "folders": folders, "files": out_files}
    out = a.out or os.path.join(folder, "file-map.draft.json")
    json.dump(res, open(out, "w"), indent=1)
    print(f"{'status':13s} {'conf':>4s}  dev  source → target")
    for sp, e in sorted(out_files.items(), key=lambda kv: (kv[1]["status"], kv[0])):
        tgt = e.get("target") or (e.get("placement") or {}).get("path") or "—"
        print(f"{e['status']:13s} {e['confidence']:4.2f}  {'ASK' if e['needs_developer'] else '   '}  {sp} → {tgt}")
        for q, x in (e.get("symbols") or {}).items():
            print(f"{'':25s}· {q} → {x['target'] or '?'}  ({x['evidence']})")
        if e.get("placement"):
            p = e["placement"]
            print(f"{'':25s}· targets: Xcode {p.get('xcode_targets') or '-'} / SPM {p.get('spm_target') or '-'} — {p.get('why', '')[:120]}")
    print(f"\nwritten: {out}\nNext: the AI reviews every entry (reads the code), fixes it, sets decided_by='ai', needs_developer only where unsure,"
          f"\nsaves it as file-map.json and re-runs collect_changes.py --map-file <report>/file-map.json")


if __name__ == "__main__":
    main()
