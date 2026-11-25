#!/usr/bin/env python3
"""
auto_decide.py — turn the AI review into decisions, and list what must go to the developer.

The agent fills these fields on every item that needs a decision (SKILL.md 1.3 / 1.35):
  recommended_option   SOURCE | TARGET | BOTH | AI | CUSTOM
  ai_confidence        0.0 – 1.0  (how sure, from the code logic)
  ai_evidence          concrete proof: "target already does X in File.swift:120", "removed on purpose in abc123 by Tara
                       ('drop legacy ping')", "no callers: git grep shows none", "same behaviour, different form" …
  escalate             true when the agent itself wants the developer (business choice, doubt)
  escalate_reason      one line
  check_verdict        agree | disagree   (independent second review — required for high-severity items)
  check_note           one line

An item is decided by the AI (decision = recommended_option, decided_by = "ai") unless one of the hard rules says
the developer must decide. Hard rules (cannot be overridden by confidence):
  * no recommended_option, or no ai_analysis / ai_recommendation
  * escalate == true
  * ai_confidence < threshold (default 0.8)
  * the second review disagreed, or a high-severity item has no second review
  * the choice DROPS source code/behaviour (TARGET on CONFLICT, SYMBOL_NOT_FOUND, DELETED_IN_TARGET, MAPPING_UNCERTAIN,
    VENDORED_BUNDLE with a newer source version, or SOURCE on DELETED_IN_SOURCE) and ai_evidence is empty
  * a protected / branch-specific file would take the SOURCE values
  * AI / BOTH chosen but proposed_code is empty
  * CUSTOM chosen (needs a human-written instruction)
Decisions a developer already made are never changed.

Usage: auto_decide.py <report>/analysis.json [--threshold 0.8]
Exit 0 = everything decided (continue automatically); 2 = escalations listed (ask the developer once, then re-run).
"""
import argparse, json, re, sys, datetime

DROPS_SOURCE = {"CONFLICT", "SYMBOL_NOT_FOUND", "DELETED_IN_TARGET", "MAPPING_UNCERTAIN", "OPTIMIZED_IN_TARGET",
                "OPTIMIZED_IN_SOURCE", "NEW_SYMBOL", "NEW_FILE", "RESTRUCTURED"}


def first_sentence(s, n=160):
    s = (s or "").strip().replace("\n", " ")
    m = re.match(r"(.+?[.!?])(\s|$)", s)
    s = m.group(1) if m else s
    return s if len(s) <= n else s[: n - 1] + "…"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("analysis")
    ap.add_argument("--threshold", type=float, default=0.8)
    a = ap.parse_args()
    d = json.load(open(a.analysis))
    decided, escalated, kept = [], [], 0
    for it in d["items"]:
        if not it.get("needs_decision"):
            continue
        if it.get("decision") and it.get("decided_by") != "ai":
            kept += 1
            continue
        cat = it.get("ai_category") or it["category"]
        rec = it.get("recommended_option")
        conf = it.get("ai_confidence")
        reasons = []
        if not rec or not it.get("ai_analysis") or not it.get("ai_recommendation"):
            reasons.append("AI review missing")
        if it.get("escalate"):
            reasons.append(it.get("escalate_reason") or "AI asked for the developer")
        if conf is None:
            reasons.append("no ai_confidence")
        elif conf < a.threshold:
            reasons.append(f"confidence {conf} < {a.threshold}")
        if it.get("check_verdict") == "disagree":
            reasons.append("independent check disagreed: " + (it.get("check_note") or ""))
        if it.get("severity") == "high" and it.get("check_verdict") not in ("agree", "disagree"):
            reasons.append("high-severity item without independent check")
        drops = (rec == "TARGET" and cat in DROPS_SOURCE) or (rec == "SOURCE" and cat == "DELETED_IN_SOURCE") or \
                (rec == "TARGET" and cat == "VENDORED_BUNDLE" and "newer" in (it.get("ai_analysis") or "").lower())
        if drops and not (it.get("ai_evidence") or "").strip():
            reasons.append("choice drops source code/behaviour but no evidence recorded")
        if (it.get("category") == "PROTECTED" or "protected file" in (it.get("signals") or [])) and rec == "SOURCE":
            reasons.append("would replace branch-specific values with source's")
        if rec in ("AI", "BOTH") and not (it.get("proposed_code") or "").strip():
            reasons.append(f"{rec} chosen without proposed_code")
        if rec == "CUSTOM":
            reasons.append("CUSTOM needs a human instruction")
        if reasons:
            it["decision"] = None if it.get("decided_by") == "ai" else it.get("decision")
            it["decided_by"] = None
            it["escalated"] = True
            it["escalation_reasons"] = reasons
            escalated.append(it)
        else:
            it["decision"] = rec
            it["decided_by"] = "ai"
            it["escalated"] = False
            it["decision_notes"] = (f"AI (confidence {conf}): {first_sentence(it.get('ai_recommendation'))}"
                                    + (f" Evidence: {first_sentence(it.get('ai_evidence'), 200)}" if it.get("ai_evidence") else ""))
            decided.append(it)
    d["auto_decide"] = {"ran_at": datetime.datetime.now().isoformat(timespec="seconds"), "threshold": a.threshold,
                        "decided_by_ai": len(decided), "escalated": len(escalated), "developer_decisions_kept": kept}
    d["status"] = "NEEDS_DEVELOPER" if escalated else "AUTO_DECIDED"
    json.dump(d, open(a.analysis, "w"), indent=1)
    print(f"decided by AI: {len(decided)} · escalated to developer: {len(escalated)} · developer decisions kept: {kept}")
    for it in escalated:
        print(f"ESCALATE {it['id']} {it.get('ai_category') or it['category']} {it.get('source_symbol') or it['file']}"
              f" — AI lean: {it.get('recommended_option') or '?'} — " + "; ".join(it["escalation_reasons"]))
    sys.exit(2 if escalated else 0)


if __name__ == "__main__":
    main()
