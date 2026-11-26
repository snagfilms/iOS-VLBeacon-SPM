#!/usr/bin/env python3
"""
parse_decisions.py — load the developers' decisions back into analysis.json.

Accepts either source (or both — the JSON wins on conflicts):
  * decisions-<ID>.json   exported from report.html
  * report.md             edited by hand ([x] on the chosen option, text after **Notes:**)

Usage:
  parse_decisions.py <report_folder>/analysis.json [decisions.json] [report.md]
  (with no extra args it looks for decisions-*.json and report.md in the report folder)

Several decisions-*.json files (one per developer, or the merge owner's combined export) are merged:
  * a combined export (has "merged_from") replaces the individual files of the reviewers it lists;
  * when the remaining files pick different options for one item → CONFLICT (ask); leaving the pre-selected
    (AI) option untouched is not a vote unless that reviewer ticked "Mark reviewed";
  * items exported with "status": "CONFLICT" (reviewers disagreed in report.html) → CONFLICT (ask);
  * notes from several reviewers are kept, each prefixed with "[name]";
  * extra keys from report.html (status, reviewed_by, reviewer_choices, reviewed, autosave, local) are tolerated;
    reviewed_by is copied onto the item.

Exit codes: 0 = every item that needs a decision has one
            2 = some required decisions are missing, ambiguous, CUSTOM without notes, or reviewers disagree
                (listed on stdout) — ask before merging
"""
import glob, json, os, re, sys, datetime

OPTIONS = ["SOURCE", "TARGET", "BOTH", "AI", "CUSTOM"]


def from_md(path):
    res, cur = {}, None
    text = open(path, encoding="utf-8").read()
    for line in text.splitlines():
        m = re.match(r"^### (M-\d{4})\b", line)
        if m:
            cur = m.group(1); continue
        if cur and line.startswith("**Decision:**"):
            picked = re.findall(r"\[[xX]\]\s*(SOURCE|TARGET|BOTH|AI|CUSTOM)", line)
            if picked:
                res.setdefault(cur, {})["choice"] = picked[0]
                if len(picked) > 1:
                    res[cur]["ambiguous"] = picked
        elif cur and line.startswith("**Notes:**"):
            n = line[len("**Notes:**"):].strip()
            if n:
                res.setdefault(cur, {})["notes"] = n
    by = re.search(r"^Decided by:\s*(.+)$", text, re.M)
    return res, (by.group(1).strip("_ ").strip() if by else "")


def main():
    apath = sys.argv[1]
    folder = os.path.dirname(os.path.abspath(apath))
    extra = sys.argv[2:]
    if not extra:
        extra = sorted(glob.glob(os.path.join(folder, "decisions-*.json"))) + [os.path.join(folder, "report.md")]
    d = json.load(open(apath))
    merged, decided_by, sources = {}, "", []
    files = []   # (path, decided_by, decisions, merged_from)
    for p in [x for x in extra if x.endswith(".md") and os.path.exists(x)] + [x for x in extra if x.endswith(".json") and os.path.exists(x)]:
        if p.endswith(".md"):
            dec, by = from_md(p)
            files.append((p, by, dec, []))
        else:
            j = json.load(open(p))
            if j.get("report_id") and j["report_id"] != d["report_id"]:
                sys.exit(f"{p} belongs to report {j['report_id']}, not {d['report_id']}")
            files.append((p, j.get("decided_by", ""), j.get("decisions", {}) or {}, j.get("merged_from") or []))
    covered = {n for _, _, _, mf in files for n in mf}          # reviewers already inside a combined export
    final = [f for f in files if f[3] or not f[1] or f[1] not in covered]
    conflicts = {}
    per_item = {}
    for p, by, dec, _ in final:
        for k, v in dec.items():
            per_item.setdefault(k, []).append((by or os.path.basename(p), v or {}))
        decided_by = by or decided_by
        sources.append(p)
    defaults = {i["id"]: i.get("decision") for i in d["items"]}
    default_notes = {i["id"]: (i.get("decision_notes") or "").strip() for i in d["items"]}   # AI / earlier decision = the pre-selected option in report.html
    for k, entries in per_item.items():
        m = merged.setdefault(k, {})
        picks, kept_default = {}, []
        for by, v in entries:
            if v.get("choice") or (v.get("notes") or "").strip() or v.get("reviewed"):
                m.setdefault("by", [])
                if by not in m["by"]:
                    m["by"].append(by)
            ch = v.get("choice")
            # leaving the pre-selected option untouched is not a vote, unless the reviewer ticked "Mark reviewed"
            if ch and (ch != defaults.get(k) or v.get("reviewed")):
                picks.setdefault(ch, []).append(by)
            elif ch:
                kept_default.append(ch)
            if v.get("ambiguous"):
                m["ambiguous"] = v["ambiguous"]
            if str(v.get("status", "")).upper() == "CONFLICT":
                rc = v.get("reviewer_choices") or {}
                conflicts[k] = ", ".join(f"{w}→{c}" for w, c in rc.items()) or "reviewers disagree (report.html)"
            for w in (v.get("reviewed_by") or []):
                m.setdefault("reviewed_by", [])
                if w not in m["reviewed_by"]:
                    m["reviewed_by"].append(w)
        if len(picks) > 1:
            conflicts[k] = ", ".join(f"{'/'.join(w)}→{c}" for c, w in picks.items())
        elif picks and k not in conflicts:
            m["choice"] = next(iter(picks))
        elif kept_default and k not in conflicts:
            m["choice"] = kept_default[0]
        # pre-filled (AI) notes left untouched are not a reviewer's note
        notes = [(by, (v.get("notes") or "").strip()) for by, v in entries
                 if (v.get("notes") or "").strip() and (v.get("notes") or "").strip() != default_notes.get(k)]
        uniq = list(dict.fromkeys(n for _, n in notes))
        if len(uniq) == 1:
            m["notes"] = uniq[0]
        elif uniq:
            m["notes"] = "\n".join(dict.fromkeys(n if n.startswith("[") else f"[{by}] {n}" for by, n in notes))

    ids = {i["id"]: i for i in d["items"]}
    unknown = [k for k in merged if k not in ids]
    for k, v in merged.items():
        if k in ids:
            if v.get("choice") in OPTIONS:
                if not (ids[k].get("decided_by") == "ai" and ids[k].get("decision") == v["choice"]):
                    ids[k]["decided_by"] = "developer"      # an override, or a decision on an escalated item
                    ids[k]["escalated"] = False
                ids[k]["decision"] = v["choice"]
            if v.get("notes"):
                ids[k]["decision_notes"] = v["notes"]
            if v.get("reviewed_by"):
                ids[k]["reviewed_by"] = v["reviewed_by"]
            if v.get("by"):
                ids[k]["reviewed_by_developer"] = v["by"]      # shown as "reviewed by <name>" in report.html
            if k in conflicts:
                ids[k].setdefault("signals", []).append(f"reviewers disagree: {conflicts[k]}")
            if v.get("ambiguous"):
                ids[k].setdefault("signals", []).append(f"report.md had several boxes ticked: {v['ambiguous']}")
    missing = [i for i in d["items"] if i["needs_decision"] and not i.get("decision")]
    custom_no_notes = [i for i in d["items"] if i.get("decision") == "CUSTOM" and not i.get("decision_notes")]
    ambiguous = [k for k, v in merged.items() if v.get("ambiguous")]
    d["decisions_meta"] = {"loaded_at": datetime.datetime.now().isoformat(timespec="seconds"), "decided_by": decided_by, "sources": sources}
    d["status"] = "DECISIONS_RECEIVED" if not (missing or conflicts) else "DECISIONS_PARTIAL"
    json.dump(d, open(apath, "w"), indent=1)

    print(f"loaded from: {', '.join(sources) or 'nothing found'}")
    print(f"decided by: {decided_by or '(not given)'}")
    counts = {}
    for i in d["items"]:
        if i.get("decision"):
            counts[i["decision"]] = counts.get(i["decision"], 0) + 1
    print("decisions: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print(f"decided by AI: {sum(1 for i in d['items'] if i.get('decided_by') == 'ai')} · by developer: "
          f"{sum(1 for i in d['items'] if i.get('decision') and i.get('decided_by') != 'ai')}")
    if unknown:
        print("WARNING unknown item ids (ignored): " + ", ".join(unknown))
    for k in ambiguous:
        print(f"AMBIGUOUS {k}: several options ticked {merged[k]['ambiguous']} — ask")
    for i in custom_no_notes:
        print(f"CUSTOM-WITHOUT-NOTES {i['id']} {i['file']} — ask what to do")
    for k, why in sorted(conflicts.items()):
        f = ids.get(k, {}).get("file", "")
        print(f"CONFLICT {k} {f} — reviewers disagree: {why} — ask which option is final")
    for i in missing:
        print(f"MISSING {i['id']} {i['category']} {i['file']} — {i['title']}")
    sys.exit(2 if (missing or ambiguous or custom_no_notes or conflicts) else 0)


if __name__ == "__main__":
    main()
