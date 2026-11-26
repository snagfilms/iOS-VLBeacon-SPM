#!/usr/bin/env python3
"""
report_server.py — open a merge report with "Ask AI" help powered by the local Cursor agent (cursor-agent).

    python3 report_server.py <report folder | analysis.json> [--open] [--port 8787] [--model <name>] [--no-ai]

What it does
  * fills in the reviewer from `git config user.name` / `user.email` (read-only on the page, saved with every decision);
  * serves the report folder (and ../index.html) on http://127.0.0.1:<port>/ — this machine only;
  * checks `cursor-agent status` (cached 60 s). The report shows the ✦ Ask AI bubble only when the agent is
    installed AND logged in; otherwise the page looks exactly like the static report;
  * answers questions about one card (or the whole report) by running
        cursor-agent -p --mode ask --output-format stream-json --stream-partial-output --resume <chat> --workspace <target repo>
    Ask mode is read-only: the agent may read files in the target repo but cannot edit anything or run commands.
    Answers stream back to the page (Server-Sent Events). Each card keeps its own Cursor chat, so follow-up
    questions keep context and `cursor-agent --resume <chat>` continues the same conversation in a terminal.

Safety
  * binds 127.0.0.1 only; rejects requests whose Host / Origin is not this server (blocks DNS rebinding and other sites);
  * every /api call needs a random per-run token that is injected only into pages this server serves;
  * the agent never gets --force / --yolo / --approve-mcps; prompts are passed as one argument (no shell);
  * questions run with the user's own Cursor login and count against their Cursor usage; code snippets from the
    report go to Cursor's servers, exactly as when using Cursor in this repository.

Settings (optional) in the target repo's .merge-guard.json:
    "ai_help": {"enabled": true, "model": "auto", "timeout_seconds": 240}
"""
import argparse, json, os, re, secrets, shutil, subprocess, sys, threading, time, urllib.parse, webbrowser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

AGENT_NAMES = ("cursor-agent", "agent")
OPTION_WORDS = {"SOURCE": "Use incoming change", "TARGET": "Keep current code (drop incoming change)", "BOTH": "Keep both",
                "AI": "Use AI's merged version", "CUSTOM": "Custom"}
STATUS_TTL = 60
MAX_Q = 4000


# ------------------------------------------------------------------ cursor-agent
def agent_path():
    for n in AGENT_NAMES:
        p = shutil.which(n) or (os.path.expanduser(f"~/.local/bin/{n}") if os.path.exists(os.path.expanduser(f"~/.local/bin/{n}")) else None)
        if p:
            return p
    return None


_status = {"at": 0, "data": None}
_status_lock = threading.Lock()


def agent_status(force=False):
    with _status_lock:
        if not force and _status["data"] and time.time() - _status["at"] < STATUS_TTL:
            return _status["data"]
        exe = agent_path()
        if not exe:
            data = {"available": False, "reason": "not-installed",
                    "hint": "Install the Cursor agent CLI (curl https://cursor.com/install -fsS | bash), then run `cursor-agent login`."}
        else:
            try:
                p = subprocess.run([exe, "status"], capture_output=True, text=True, timeout=25)
                out = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", (p.stdout or "") + (p.stderr or ""))
                m = re.search(r"Logged in as\s+(\S+)", out)
                if p.returncode == 0 and m:
                    team = re.search(r"Team:\s*(.+)", out)
                    data = {"available": True, "account": m.group(1), "team": team.group(1).strip() if team else ""}
                else:
                    data = {"available": False, "reason": "not-logged-in", "hint": "Run `cursor-agent login` in a terminal, then reload this page."}
            except (subprocess.TimeoutExpired, OSError) as e:
                data = {"available": False, "reason": "status-failed", "hint": f"`cursor-agent status` failed: {e}"}
        _status.update(at=time.time(), data=data)
        return data


def git_identity(repo):
    """The reviewer's name/email from git config (repo settings first, then global) — shown read-only in the report."""
    def cfg(key):
        try:
            p = subprocess.run(["git", "-C", repo, "config", "--get", key], capture_output=True, text=True, timeout=10)
            return p.stdout.strip() if p.returncode == 0 else ""
        except (OSError, subprocess.TimeoutExpired):
            return ""
    name, email = cfg("user.name"), cfg("user.email")
    return {"name": name, "email": email, "source": "git config"} if name else None


def create_chat(exe):
    p = subprocess.run([exe, "create-chat"], capture_output=True, text=True, timeout=30)
    m = re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", p.stdout or "")
    if not m:
        raise RuntimeError("could not create a Cursor chat: " + ((p.stderr or p.stdout or "").strip()[:200]))
    return m[-1]


# ------------------------------------------------------------------ prompt building
def load_json(p):
    try:
        return json.load(open(p))
    except (OSError, json.JSONDecodeError):
        return None


def snippet(title, snip, limit=60):
    if not snip or not snip.get("lines"):
        return f"{title}: (not present)\n"
    mk = set(snip.get("marked") or [])
    rows = [f"{'»' if i in mk else ' '} {snip['start'] + i:5d} | {l}" for i, l in enumerate(snip["lines"][:limit])]
    return f"{title} (from line {snip['start']}; » = changed):\n```\n" + "\n".join(rows) + "\n```\n"


def card_context(ctx, item_id):
    d = ctx["analysis"]
    it = next((i for i in d["items"] if i["id"] == item_id), None)
    if not it:
        raise KeyError(f"unknown card {item_id}")
    q = ((ctx.get("quality") or {}).get("items") or {}).get(item_id) or {}
    fq = ((ctx.get("quality") or {}).get("files") or {}).get(it.get("target_path") or it["file"]) or {}
    v = next((r for r in ((ctx.get("verification") or {}).get("results") or []) if r.get("id") == item_id), None)
    cat = it.get("ai_category") or it["category"]
    dec = it.get("decision")
    lines = [f"Card {item_id} — {cat} — {it.get('title')}",
             f"File in current branch: {it.get('target_path') or '(not found)'}   (incoming path: {it['file']})",
             f"Severity: {it.get('severity')}"]
    if dec:
        lines.append(f"Current decision: {OPTION_WORDS.get(dec, dec)} ({dec}), decided by {it.get('decided_by') or 'developer'}"
                     + (f" — note: {it['decision_notes']}" if it.get("decision_notes") else ""))
    if it.get("recommended_option"):
        lines.append(f"AI suggestion: {OPTION_WORDS.get(it['recommended_option'], it['recommended_option'])} "
                     f"(confidence {it.get('ai_confidence')})")
    if it.get("check_verdict"):
        lines.append(f"Independent second check: {it['check_verdict']} — {it.get('check_note') or ''}")
    for k, lab in (("ai_analysis", "AI analysis"), ("ai_recommendation", "AI recommendation"), ("ai_evidence", "Evidence")):
        if it.get(k):
            lines.append(f"{lab}: {it[k]}")
    if it.get("escalation_reasons"):
        lines.append("Why it needs a person: " + "; ".join(it["escalation_reasons"]))
    if it.get("signals"):
        lines.append("Signals: " + "; ".join(it["signals"]))
    for side, key in (("Incoming lines written by", "source_authors"), ("Current lines written by", "target_authors")):
        a = it.get(key) or []
        if a:
            lines.append(f"{side}: " + ", ".join(f"{x.get('name')} ({x.get('short')}, {x.get('date', '')[:10]}: {x.get('subject')})" for x in a[:3]))
    if v:
        lines.append(f"Verification after the merge: {v.get('status')}"
                     + (f"; MISSING lines: {v['missing'][:6]}" if v.get("missing") else "")
                     + (f"; removed lines still present: {v['still_present'][:6]}" if v.get("still_present") else ""))
    if q.get("platform"):
        lines.append("Platform context: " + ", ".join(q["platform"]))
    if q.get("functions"):
        lines.append(f"Changed function(s): {', '.join(q['functions'])} — {q.get('callers_total', 0)} call sites, e.g. "
                     + "; ".join(f"{c['file']}:{c['line']}" for c in (q.get("callers") or [])[:6]))
    if q.get("lint"):
        lines.append("New SwiftLint warnings on merged lines: " + "; ".join(f"L{x['line']} {x['rule']}" for x in q["lint"]))
    if fq:
        lines.append(f"File risk {fq.get('score')}/100 ({fq.get('commits')} commits, {fq.get('authors')} authors recently; tests: {fq.get('tested') or 'none'})")
    body = "\n".join(lines) + "\n\n"
    body += snippet("Base (last common commit)", it.get("base"))
    body += snippet(f"Incoming ({d['source']['branch']})", it.get("source"))
    body += snippet(f"Current ({d['target']['branch']})", it.get("target"))
    if it.get("proposed_code"):
        body += f"AI's merged version:\n```{it.get('proposed_language') or ''}\n{it['proposed_code']}\n```\n"
    return body


def report_context(ctx):
    d = ctx["analysis"]
    v = ctx.get("verification") or {}
    b = ctx.get("build") or {}
    rows = []
    for i in d["items"]:
        if (i.get("ai_category") or i["category"]) in ("ALREADY_PRESENT", "COSMETIC", "IB_METADATA", "JUNK"):
            continue
        rows.append(f"- {i['id']} {i.get('ai_category') or i['category']} {i.get('target_path') or i['file']} → "
                    f"{OPTION_WORDS.get(i.get('decision'), i.get('decision') or 'undecided')}"
                    + (" [needs a person]" if i.get("needs_decision") and not i.get("decision") else ""))
    out = [f"Report {d['report_id']}: {len(d['items'])} changes, status {d.get('status')}.",
           f"Verification: {'PASS' if v.get('ok') else 'FAIL' if v else 'not run'}"
           + (f", {v.get('missing_items')} items lost lines" if v.get("missing_items") else "")
           + (f", {v.get('still_present_items')} with removed lines still present" if v.get("still_present_items") else ""),
           "Build: " + (", ".join(f"{r['scheme']} {r['status']}" for r in b.get("results") or []) or "not run")]
    miss = ((ctx.get("quality") or {}).get("build_missing_modules")) or []
    if miss:
        out.append("Build logs could not resolve modules: " + ", ".join(m["module"] for m in miss))
    return "\n".join(out) + "\n\nItems:\n" + "\n".join(rows[:150]) + "\n"


def build_prompt(ctx, scope, card_id, question, first):
    d = ctx["analysis"]
    head = ("You are helping a developer review a branch merge in this repository. This is read-only Q&A: never edit files or run commands.\n"
            f"Merge: incoming branch `{d['source']['branch']}` → current branch `{d['target']['branch']}` (report {d['report_id']}).\n"
            "The developer chooses per card between: \"Use incoming change\", \"Keep current code (drop incoming change)\", \"Keep both\", "
            "\"Use AI's merged version\", \"Custom\".\n"
            "Answer plainly for a developer: short paragraphs or bullets, lead with the answer, cite code as path:line, "
            "read more files in the workspace when the snippets are not enough, and say clearly when you are not sure. "
            "Do not invent code that is not in the repository.\n\n")
    if not first:
        return f"(Follow-up about {'card ' + card_id if scope == 'card' else 'the whole report'}.)\n\n{question}"
    ctxt = card_context(ctx, card_id) if scope == "card" else report_context(ctx)
    return head + "=== Context ===\n" + ctxt + "\n=== Question ===\n" + question


# ------------------------------------------------------------------ HTTP
class Ctx:
    pass


def make_handler(C):
    class H(SimpleHTTPRequestHandler):
        server_version = "merge-report"

        def __init__(self, *a, **kw):
            super().__init__(*a, directory=C.root, **kw)

        def log_message(self, fmt, *args):
            if C.verbose:
                sys.stderr.write("%s\n" % (fmt % args))

        # ---- guards
        def host_ok(self):
            h = (self.headers.get("Host") or "").lower()
            return h in (f"127.0.0.1:{C.port}", f"localhost:{C.port}")

        def origin_ok(self):
            o = self.headers.get("Origin")
            return o is None or o in (f"http://127.0.0.1:{C.port}", f"http://localhost:{C.port}")

        def api_ok(self):
            return self.host_ok() and self.origin_ok() and secrets.compare_digest(self.headers.get("X-Report-Token") or "", C.token)

        def send_json(self, code, obj):
            b = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def end_headers(self):
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            super().end_headers()

        # ---- static files (+ bridge injection into HTML)
        def do_GET(self):
            if not self.host_ok():
                return self.send_error(403, "Forbidden host")
            u = urllib.parse.urlparse(self.path)
            if u.path == "/":
                self.send_response(302)
                self.send_header("Location", f"/{C.report_rel}/report.html")
                return self.end_headers()
            if u.path == "/api/ai/status":
                if not self.api_ok():
                    return self.send_json(403, {"error": "forbidden"})
                st = dict(agent_status(force="refresh" in u.query))
                st.update(enabled=C.enabled, model=C.model or "Cursor default", workspace=C.workspace)
                return self.send_json(200, st)
            if u.path.endswith(".html"):
                fp = os.path.realpath(os.path.join(C.root, urllib.parse.unquote(u.path).lstrip("/")))
                if not fp.startswith(C.root + os.sep) or not os.path.isfile(fp):
                    return self.send_error(404)
                html = open(fp, encoding="utf-8", errors="replace").read()
                bridge = json.dumps({"token": C.token, "workspace": C.workspace, "enabled": C.enabled, "reviewer": C.reviewer}).replace("</", "<\\/")
                html = html.replace("</head>", f"<script>window.__AI_BRIDGE={bridge};</script></head>", 1)
                b = html.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                return self.wfile.write(b)
            if u.path.startswith("/api/"):
                return self.send_error(404)
            return super().do_GET()

        def do_HEAD(self):
            return self.send_error(405)

        # ---- ask (Server-Sent Events)
        def do_POST(self):
            u = urllib.parse.urlparse(self.path)
            if u.path != "/api/ai/ask" or not self.api_ok():
                return self.send_json(403, {"error": "forbidden"})
            if not C.enabled:
                return self.send_json(409, {"error": "AI help is disabled in .merge-guard.json"})
            st = agent_status()
            if not st.get("available"):
                return self.send_json(409, {"error": st.get("hint") or "Cursor agent not available"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
                req = json.loads(self.rfile.read(min(n, 64000)) or b"{}")
            except (ValueError, json.JSONDecodeError):
                return self.send_json(400, {"error": "bad request"})
            question = str(req.get("question") or "").strip()[:MAX_Q]
            scope = "report" if req.get("scope") == "report" else "card"
            card = str(req.get("card_id") or "")
            chat = str(req.get("chat_id") or "")
            if not question or (scope == "card" and not re.fullmatch(r"M-\d{1,6}", card)) or (chat and not re.fullmatch(r"[0-9a-f-]{36}", chat)):
                return self.send_json(400, {"error": "bad request"})
            C.reload()
            try:
                first = not chat
                if first:
                    chat = create_chat(C.exe)
                prompt = build_prompt(C.ctx, scope, card, question, first)
            except (KeyError, RuntimeError, subprocess.TimeoutExpired) as e:
                return self.send_json(400, {"error": str(e)})

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()

            def emit(ev, data):
                self.wfile.write(f"event: {ev}\ndata: {json.dumps(data)}\n\n".encode())
                self.wfile.flush()

            cmd = [C.exe, "-p", "--mode", "ask", "--output-format", "stream-json", "--stream-partial-output",
                   "--resume", chat, "--workspace", C.workspace, "--trust"] + (["--model", C.model] if C.model else []) + [prompt]
            proc = None
            try:
                emit("meta", {"chat_id": chat, "first": first})
                proc = subprocess.Popen(cmd, cwd=C.workspace, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
                killer = threading.Timer(C.timeout, proc.kill)
                killer.start()
                final, got = "", ""
                for line in proc.stdout:
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    t = ev.get("type")
                    if t == "assistant" and ev.get("timestamp_ms"):
                        txt = "".join(c.get("text", "") for c in (ev.get("message") or {}).get("content") or [] if c.get("type") == "text")
                        if txt:
                            got += txt
                            emit("delta", {"text": txt})
                    elif t == "tool_call":
                        tc = ev.get("tool_call") or {}
                        name = next(iter(tc.keys()), "tool")
                        args = (tc.get(name) or {}).get("args") or {}
                        detail = args.get("path") or args.get("pattern") or args.get("query") or ""
                        if ev.get("subtype") == "started":
                            emit("tool", {"name": re.sub(r"ToolCall$", "", name), "detail": str(detail)[-120:]})
                    elif t == "result":
                        final = ev.get("result") or got
                        emit("done", {"text": final, "chat_id": chat, "ms": ev.get("duration_ms"), "error": bool(ev.get("is_error"))})
                proc.wait(timeout=10)
                killer.cancel()
                if not final:
                    err = (proc.stderr.read() or "").strip()[-400:]
                    emit("error", {"message": "The Cursor agent stopped without an answer" + (f": {err}" if err else
                                   (" (timed out)" if proc.returncode in (-9, 137) else ""))})
            except (BrokenPipeError, ConnectionResetError):
                pass                                    # the page closed or the user pressed Stop
            except Exception as e:                       # report, never crash the server
                try:
                    emit("error", {"message": str(e)[:300]})
                except OSError:
                    pass
            finally:
                if proc and proc.poll() is None:
                    proc.kill()
    return H


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("report", help="report folder or its analysis.json")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--open", action="store_true", help="open the report in the default browser")
    ap.add_argument("--model", default=None, help="Cursor model (default: .merge-guard.json ai_help.model, else Cursor's default)")
    ap.add_argument("--no-ai", action="store_true", help="serve the report without AI help")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    folder = os.path.realpath(a.report if os.path.isdir(a.report) else os.path.dirname(a.report))
    ap_json = os.path.join(folder, "analysis.json")
    if not os.path.exists(ap_json):
        sys.exit(f"no analysis.json in {folder}")
    C = Ctx()
    C.root = os.path.dirname(folder)                       # serve the reports folder, so ../index.html works
    C.report_rel = urllib.parse.quote(os.path.basename(folder))
    C.token = secrets.token_urlsafe(32)
    C.verbose = a.verbose

    def reload():
        C.ctx = {"analysis": load_json(ap_json), "quality": load_json(os.path.join(folder, "quality.json")),
                 "verification": load_json(os.path.join(folder, "verification.json")),
                 "build": load_json(os.path.join(folder, "build-summary.json"))}
    C.reload = reload
    reload()
    t = C.ctx["analysis"]["target"]
    C.workspace = t.get("repo_root") or t.get("folder")
    cfg = (load_json(os.path.join(C.workspace, ".merge-guard.json")) or {}).get("ai_help") or {}
    C.enabled = (not a.no_ai) and cfg.get("enabled", True) is not False
    C.model = a.model or (cfg.get("model") if cfg.get("model") not in (None, "", "auto") else None)
    C.timeout = int(cfg.get("timeout_seconds") or 240)
    C.exe = agent_path()
    C.reviewer = git_identity(C.workspace)

    srv = None
    for port in range(a.port, a.port + 20):
        try:
            C.port = port
            srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(C))
            break
        except OSError:
            continue
    if not srv:
        sys.exit("no free port")
    srv.daemon_threads = True
    url = f"http://127.0.0.1:{C.port}/{C.report_rel}/report.html"
    st = agent_status() if C.enabled else {"available": False, "reason": "disabled"}
    print(f"Merge report: {url}")
    print("Reviewer: " + (f"{C.reviewer['name']} (from git config)" if C.reviewer else "not set in git config — the page will ask for a name"))
    print("AI help: " + (f"ON — Cursor agent logged in as {st.get('account')}" if st.get("available") else
                         f"OFF — {st.get('hint') or st.get('reason')}"))
    print("Press Ctrl+C to stop.")
    if a.open:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
