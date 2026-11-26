#!/usr/bin/env python3
"""
auto_decide.py — turn the AI review into decisions, and list what must go back to the AI or to the developer.

The agent fills these fields (SKILL.md 1.3 / 1.35), ideally through apply_review.py so every change is in ai_history:
  recommended_option   SOURCE | TARGET | BOTH | AI | CUSTOM
  ai_confidence        0.0 – 1.0  (how sure, from the code logic)
  ai_evidence          concrete proof: "target already does X in File.swift:120", "removed on purpose in abc123 by Tara
                       ('drop legacy ping')", "no callers: git grep shows none", "same behaviour, different form" …
  escalate             true when the agent itself wants the developer (business choice, doubt)
  escalate_reason      one line
  external_dependency  set when correctness depends on something outside the repo → always escalated
  check_verdict        agree | disagree   (independent second review)
  check_note           what the second reviewer actually verified (a real sentence, not "Agrees.")
  check_by             who did the second review (sub-agent name / "second pass" / "rule")
  depends_on           ["M-0132", …] items this decision relies on (ids mentioned in the AI text are added too)
  counterpart_verdict  port | not-needed   — required when classify_items.py found a look-alike (`counterparts`)
  counterpart_note     where it is ported / why not needed
  change_reason        required when a review clears an earlier doubt (see below)

Which items: every item that needs a decision, AND every reviewed item outside "needs decision" (Review cards such
as NEAR_CHANGE / PROJECT_FILE / NEW_FILE / IB_METADATA) — so an AI recommendation that is not "take source" becomes
a recorded decision the merge must follow, instead of being silently overridden by git's auto-merge.

Outcome per item:
  decided    decision = recommended_option, decided_by = "ai"
  RECHECK    the AI's own work is incomplete — the agent must fix it and re-run (exit 3), never the developer:
               · independent check missing or boilerplate ("Agrees.", "Adopted agent recommendation…") on a
                 high-severity item or on a choice that drops / rewrites source code
               · a look-alike in a parallel module (counterparts) without counterpart_verdict / counterpart_note
  ESCALATE   a person must decide (exit 2). Hard rules (confidence never overrides them):
               · no recommended_option, or no ai_analysis / ai_recommendation
               · escalate == true, or an external_dependency is recorded
               · ai_confidence < threshold (default 0.8)
               · the second review disagreed
               · an earlier review of this item was doubtful (escalated / CUSTOM / below threshold) and the current
                 one clears it without change_reason, or the doubt was cleared by a self-check only
               · the choice drops source code/behaviour without ai_evidence
               · a protected / branch-specific file would take the SOURCE values
               · AI / BOTH chosen but proposed_code is empty
               · CUSTOM chosen (needs a human-written instruction)
               · depends on an item that is escalated (follows its answer)
               · target reverted this change on purpose (risk_scan.py: reverted_in_target) — source would bring it back
               · source adds something that looks like a credential (risk_scan.py: secret)
Decisions a developer already made are never changed. Direct edits to analysis.json are detected (compared with
the last recorded state) and added to ai_history as "edited directly".

Usage: auto_decide.py <report>/analysis.json [--threshold 0.8]
Exit 0 = everything decided · 2 = escalations (ask the developer once, then re-run) · 3 = RECHECK (AI work first)
"""
import argparse, json, re, sys, datetime

DROPS_SOURCE = {"CONFLICT", "SYMBOL_NOT_FOUND", "DELETED_IN_TARGET", "MAPPING_UNCERTAIN", "OPTIMIZED_IN_TARGET",
                "OPTIMIZED_IN_SOURCE", "NEW_SYMBOL", "NEW_FILE", "RESTRUCTURED", "NEAR_CHANGE", "PROJECT_FILE"}
BOILER = re.compile(r"^\s*(agree[sd]?|ok|okay|lgtm|same|fine|looks good|confirmed|n/?a|-)?\s*[.!]?\s*$"
                    r"|adopted (the )?agent|second pass settled|standard .{0,30} rule|same as m-\d{4}\s*\.?$", re.I)
SELF_CHECK = re.compile(r"second pass|self[- ]check|re-?read myself", re.I)
IDS = re.compile(r"\bM-\d{4}\b")


def first_sentence(s, n=160):
    s = (s or "").strip().replace("\n", " ")
    m = re.match(r"(.+?[.!?])(\s|$)", s)
    s = m.group(1) if m else s
    return s if len(s) <= n else s[: n - 1] + "…"


def weak_check(it):
    if it.get("check_by") == "rule":
        return False
    note = (it.get("check_note") or "").strip()
    return it.get("check_verdict") not in ("agree", "disagree") or len(note) < 30 or bool(BOILER.search(note))


def doubtful(x, thr):
    c = x.get("ai_confidence")
    return bool(x.get("escalate")) or x.get("recommended_option") == "CUSTOM" or (c is not None and c < thr)


def track_direct_edits(it, now):
    if not it.get("recommended_option"):
        return
    h = it.setdefault("ai_history", [])
    cur = {k: it.get(k) for k in ("recommended_option", "ai_confidence", "escalate", "check_verdict")}
    if not h or any(h[-1].get(k) != v for k, v in cur.items()):
        e = {"at": now, "source": "analysis.json (edited directly)" if h else "analysis.json (first auto_decide run)"}
        e.update({k: v for k, v in cur.items() if v is not None})
        if it.get("change_reason"):
            e["change_reason"] = it["change_reason"]
        h.append(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("analysis")
    ap.add_argument("--threshold", type=float, default=0.8)
    a = ap.parse_args()
    thr = a.threshold
    d = json.load(open(a.analysis))
    now = datetime.datetime.now().isoformat(timespec="seconds")
    ids = {i["id"]: i for i in d["items"]}
    decided, escalated, recheck, kept = [], [], [], 0

    def in_scope(it):
        return it.get("needs_decision") or it.get("recommended_option") or it.get("counterparts")

    results = {}
    for it in d["items"]:
        if not in_scope(it):
            continue
        track_direct_edits(it, now)
        if it.get("decision") and it.get("decided_by") not in ("ai", None):
            kept += 1
            continue
        cat = it.get("ai_category") or it["category"]
        rec = it.get("recommended_option")
        conf = it.get("ai_confidence")
        reviewed = bool(rec or it.get("ai_analysis"))
        deps = set(it.get("depends_on") or [])
        for k in ("ai_recommendation", "ai_evidence", "check_note", "escalate_reason"):
            deps |= set(IDS.findall(it.get(k) or ""))
        deps.discard(it["id"])
        deps = sorted(x for x in deps if x in ids)
        if deps:
            it["depends_on"] = deps
        reasons, rc = [], []
        # ---- look-alikes in parallel modules: the AI must look at them
        if it.get("counterparts"):
            v = (it.get("counterpart_verdict") or "").lower()
            if v not in ("port", "not-needed") or len((it.get("counterpart_note") or "").strip()) < 15:
                rc.append("look-alike in a parallel module not checked: " +
                          ", ".join(c["path"] for c in it["counterparts"]) + " → set counterpart_verdict + counterpart_note")
        if not reviewed:
            if not it.get("needs_decision"):      # e.g. a CLEAN item that only needed the look-alike check
                results[it["id"]] = ("recheck" if rc else "skip", reasons, rc)
                continue
            reasons.append("AI review missing")
        else:
            if not rec or not it.get("ai_analysis") or not it.get("ai_recommendation"):
                reasons.append("AI review missing")
            if it.get("escalate"):
                reasons.append(it.get("escalate_reason") or "AI asked for the developer")
            if (it.get("external_dependency") or "").strip():
                reasons.append("depends on an external contract the repo can't prove: " + it["external_dependency"])
            if conf is None:
                reasons.append("no ai_confidence")
            elif conf < thr:
                reasons.append(f"confidence {conf} < {thr}")
            if it.get("check_verdict") == "disagree":
                reasons.append("independent check disagreed: " + (it.get("check_note") or ""))
            drops = (rec == "TARGET" and cat in DROPS_SOURCE) or (rec == "SOURCE" and cat == "DELETED_IN_SOURCE") or \
                    (rec == "TARGET" and cat == "VENDORED_BUNDLE" and "newer" in (it.get("ai_analysis") or "").lower())
            rewrites = rec in ("AI", "BOTH")
            if drops and not (it.get("ai_evidence") or "").strip():
                reasons.append("choice drops source code/behaviour but no evidence recorded")
            if weak_check(it) and (it.get("severity") == "high" or drops or rewrites):
                rc.append("independent check missing or boilerplate (" + repr((it.get("check_note") or "")[:50]) +
                          ") — redo it: separate reviewer, without your conclusion, try to prove the opposite")
            # ---- earlier doubt cleared?
            hist = it.get("ai_history") or []
            earlier = [x for x in hist[:-1] if doubtful(x, thr)]
            if earlier and not doubtful(it, thr):
                e = earlier[-1]
                was = f"{e.get('recommended_option')} {e.get('ai_confidence')}" + (" escalated" if e.get("escalate") else "")
                if len((it.get("change_reason") or "").strip()) < 20:
                    reasons.append(f"an earlier review was doubtful ({was}, {e.get('source')}) and was cleared without change_reason")
                elif SELF_CHECK.search(it.get("check_note") or "") or SELF_CHECK.search(it.get("check_by") or ""):
                    reasons.append(f"earlier doubt ({was}) cleared by a self-check only — needs a separate reviewer or the developer")
                it["doubt_cleared"] = was
            if (it.get("category") == "PROTECTED" or "protected file" in (it.get("signals") or [])) and rec == "SOURCE":
                reasons.append("would replace branch-specific values with source's")
            if rewrites and not (it.get("proposed_code") or "").strip():
                reasons.append(f"{rec} chosen without proposed_code")
            if rec == "CUSTOM":
                reasons.append("CUSTOM needs a human instruction")
        for rv in it.get("reverted_in_target") or []:
            if rec != "TARGET" or not it.get("ai_evidence"):
                reasons.append(f"target reverted this on purpose in {rv['commit']} ('{rv['subject'][:60]}') — confirm it should come back")
        if it.get("secret"):
            reasons.append(f"source adds what looks like a {it['secret']} — the owner must confirm it may be committed")
        results[it["id"]] = ("esc" if reasons else "recheck" if rc else "ok", reasons, rc)

    # ---- dependencies: follow an escalated item
    changed = True
    while changed:
        changed = False
        for iid, (state, reasons, rc) in results.items():
            if state in ("esc", "skip"):
                continue
            bad = [x for x in ids[iid].get("depends_on") or [] if results.get(x, ("",))[0] == "esc"]
            if bad:
                reasons.append("depends on " + ", ".join(bad) + ", which needs a developer — follows that answer")
                results[iid] = ("esc", reasons, rc)
                changed = True

    for iid, (state, reasons, rc) in results.items():
        it = ids[iid]
        it["recheck"] = rc or None
        if state == "skip":
            continue
        if state == "ok":
            it["decision"] = it.get("recommended_option")
            it["decided_by"] = "ai"
            it["escalated"] = False
            it["escalation_reasons"] = None
            conf = it.get("ai_confidence")
            it["decision_notes"] = (f"AI (confidence {conf}): {first_sentence(it.get('ai_recommendation'))}"
                                    + (f" Evidence: {first_sentence(it.get('ai_evidence'), 200)}" if it.get("ai_evidence") else ""))
            decided.append(it)
            continue
        if it.get("decided_by") == "ai":
            it["decision"] = None
            it["decided_by"] = None
        if state == "esc":
            it["escalated"] = True
            it["escalation_reasons"] = reasons
            it["needs_decision"] = True          # review items that escalate move to "Needs you"
            escalated.append(it)
        else:
            it["escalated"] = False
            recheck.append(it)

    d["auto_decide"] = {"ran_at": now, "threshold": thr, "decided_by_ai": len(decided), "escalated": len(escalated),
                        "recheck": len(recheck), "developer_decisions_kept": kept}
    d["status"] = "AI_RECHECK" if recheck else ("NEEDS_DEVELOPER" if escalated else "AUTO_DECIDED")
    json.dump(d, open(a.analysis, "w"), indent=1)
    print(f"decided by AI: {len(decided)} · AI re-check needed: {len(recheck)} · escalated to developer: {len(escalated)}"
          f" · developer decisions kept: {kept}")
    for it in recheck:
        print(f"RECHECK {it['id']} {it.get('ai_category') or it['category']} {it['file']} — " + "; ".join(it["recheck"]))
    for it in escalated:
        print(f"ESCALATE {it['id']} {it.get('ai_category') or it['category']} {it.get('source_symbol') or it['file']}"
              f" — AI lean: {it.get('recommended_option') or '?'} — " + "; ".join(it["escalation_reasons"]))
    sys.exit(3 if recheck else 2 if escalated else 0)


if __name__ == "__main__":
    main()
