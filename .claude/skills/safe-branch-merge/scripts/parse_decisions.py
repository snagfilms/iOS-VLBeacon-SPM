#!/usr/bin/env python3
"""
parse_decisions.py — load the developers' decisions back into analysis.json.

Accepts either source (or both — the JSON wins on conflicts):
  * decisions-<ID>.json   exported from report.html
  * report.md             edited by hand ([x] on the chosen option, text after **Notes:**)

Usage:
  parse_decisions.py <report_folder>/analysis.json [decisions.json] [report.md]
  (with no extra args it looks for decisions-*.json and report.md in the report folder)

Exit codes: 0 = every item that needs a decision has one
            2 = some required decisions are missing (listed on stdout) — ask before merging
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
    for p in [x for x in extra if x.endswith(".md") and os.path.exists(x)] + [x for x in extra if x.endswith(".json") and os.path.exists(x)]:
        if p.endswith(".md"):
            dec, by = from_md(p)
        else:
            j = json.load(open(p))
            if j.get("report_id") and j["report_id"] != d["report_id"]:
                sys.exit(f"{p} belongs to report {j['report_id']}, not {d['report_id']}")
            dec, by = j.get("decisions", {}), j.get("decided_by", "")
        for k, v in dec.items():
            merged.setdefault(k, {}).update({kk: vv for kk, vv in v.items() if vv})
        decided_by = by or decided_by
        sources.append(p)

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
            if v.get("ambiguous"):
                ids[k].setdefault("signals", []).append(f"report.md had several boxes ticked: {v['ambiguous']}")
    missing = [i for i in d["items"] if i["needs_decision"] and not i.get("decision")]
    custom_no_notes = [i for i in d["items"] if i.get("decision") == "CUSTOM" and not i.get("decision_notes")]
    ambiguous = [k for k, v in merged.items() if v.get("ambiguous")]
    d["decisions_meta"] = {"loaded_at": datetime.datetime.now().isoformat(timespec="seconds"), "decided_by": decided_by, "sources": sources}
    d["status"] = "DECISIONS_RECEIVED" if not missing else "DECISIONS_PARTIAL"
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
    for i in missing:
        print(f"MISSING {i['id']} {i['category']} {i['file']} — {i['title']}")
    sys.exit(2 if (missing or ambiguous or custom_no_notes) else 0)


if __name__ == "__main__":
    main()
