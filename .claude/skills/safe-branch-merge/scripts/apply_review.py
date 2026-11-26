#!/usr/bin/env python3
"""
apply_review.py — merge AI review results (from sub-agents / batches) into analysis.json, keeping a history.

Every review result changes an item's AI fields. Without a history, a low-confidence or escalated review can be
silently replaced by a confident one and never reach the developer. This script is the only way review results
should enter analysis.json: each change is appended to the item's `ai_history`, and auto_decide.py refuses to
clear an earlier doubt (escalate / CUSTOM / confidence below the threshold) unless the new review gives a
`change_reason` and has a real independent check.

Result files: a JSON list of items, or {"items": [...], "reviewer": "<name>"}; each item has "id" plus any of
  ai_category ai_analysis ai_recommendation recommended_option proposed_code proposed_language ai_evidence
  ai_confidence escalate escalate_reason external_dependency check_verdict check_note check_by
  depends_on counterpart_verdict counterpart_note change_reason

Usage:
  apply_review.py <report>/analysis.json results.json [more.json …] [--by reviewer-name]
  apply_review.py <report>/analysis.json review-queue/*.results.json --history-only
      (record earlier batch results as history without changing the current fields — use it to audit a report
       whose analysis.json was edited by hand)
"""
import argparse, datetime, json, os

FIELDS = ["ai_category", "ai_analysis", "ai_recommendation", "recommended_option", "proposed_code", "proposed_language",
          "ai_evidence", "ai_confidence", "escalate", "escalate_reason", "external_dependency", "check_verdict",
          "check_note", "check_by", "depends_on", "counterpart_verdict", "counterpart_note", "change_reason"]
SNAP = ["recommended_option", "ai_confidence", "escalate", "check_verdict", "change_reason"]


def snapshot(src, at, source, by):
    s = {"at": at, "source": source}
    if by:
        s["by"] = by
    for k in SNAP:
        if src.get(k) is not None:
            s[k] = src.get(k)
    if src.get("escalate_reason"):
        s["escalate_reason"] = src["escalate_reason"]
    return s


def same(a, b):
    return all(a.get(k) == b.get(k) for k in ("recommended_option", "ai_confidence", "escalate", "check_verdict"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("analysis")
    ap.add_argument("results", nargs="+")
    ap.add_argument("--by", default="")
    ap.add_argument("--history-only", action="store_true")
    a = ap.parse_args()
    d = json.load(open(a.analysis))
    ids = {i["id"]: i for i in d["items"]}
    now = datetime.datetime.now().isoformat(timespec="seconds")
    applied, unknown = 0, []
    for path in a.results:
        j = json.load(open(path))
        rows = j.get("items", []) if isinstance(j, dict) else j
        by = a.by or (j.get("reviewer") if isinstance(j, dict) else "") or ""
        at = datetime.datetime.fromtimestamp(os.path.getmtime(path)).isoformat(timespec="seconds") if a.history_only else now
        for r in rows:
            it = ids.get(r.get("id"))
            if not it:
                unknown.append(r.get("id")); continue
            h = it.setdefault("ai_history", [])
            if not h and it.get("recommended_option") and not a.history_only:
                h.append(snapshot(it, now, "analysis.json before apply_review", ""))
            snap = snapshot(r, at, os.path.basename(path), by)
            if a.history_only:
                if not any(x.get("source") == snap["source"] and same(x, snap) for x in h):
                    h.append(snap)
                    h.sort(key=lambda x: x.get("at", ""))
                continue
            for k in FIELDS:
                if k in r:
                    it[k] = r[k]
            if not h or not same(h[-1], snap):
                h.append(snap)
            applied += 1
    json.dump(d, open(a.analysis, "w"), indent=1)
    print(("recorded history for" if a.history_only else "applied") + f" {len(a.results)} file(s); items updated: {applied}")
    if unknown:
        print("WARNING unknown ids: " + ", ".join(map(str, unknown)))
    print("Next: auto_decide.py — it checks every history for doubts cleared without a reason.")


if __name__ == "__main__":
    main()
