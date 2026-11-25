#!/usr/bin/env python3
"""
symbols.py — lightweight declaration index for Swift, Objective-C, Kotlin, Java, JS/TS, C#, Go.
Used to compare code by FUNCTION / TYPE instead of by file when files were moved, split or merged.

  index(text, lang) -> [Symbol]   kind, name, key (name + parameter labels), qual (Container.key), start, end (0-based, inclusive)
  enclosing(symbols, line0, line1) -> innermost symbol covering the range (functions preferred over types)
  body(text, sym) -> list of lines

CLI (debug):  symbols.py <file>   → prints the index
Heuristic (brace matching, strings/comments skipped); good enough to locate code, not a compiler.
"""
import re, sys
from dataclasses import dataclass, field

LANG_BY_EXT = {".swift": "swift", ".m": "objc", ".mm": "objc", ".h": "objc", ".kt": "kotlin", ".java": "java",
               ".js": "js", ".jsx": "js", ".ts": "js", ".tsx": "js", ".cs": "csharp", ".go": "go"}

MOD = r"(?:@[\w.]+(?:\([^)]*\))?\s+)*(?:(?:public|private|fileprivate|internal|open|final|static|class|override|required|convenience|mutating|nonisolated|async|dynamic|lazy|weak|unowned|indirect|protected|abstract|suspend|inline|export|default|readonly|virtual|sealed|partial|data|inner|operator|infix|tailrec|external|const|let|var)\s+)*"
PATTERNS = {
    "swift": [
        ("type", re.compile(r"^\s*" + MOD + r"(class|struct|enum|protocol|actor|extension)\s+([A-Za-z_][\w.]*)")),
        ("func", re.compile(r"^\s*" + MOD + r"func\s+([^\s(<]+)\s*(?:<[^>]*>)?\s*\(([^)]*)\)?")),
        ("init", re.compile(r"^\s*" + MOD + r"(init|deinit)[?!]?\s*(?:<[^>]*>)?\s*(?:\(([^)]*)\)?)?")),
        ("var", re.compile(r"^\s*" + MOD + r"(?:var|let)\s+([A-Za-z_]\w*)\s*[:=][^{]*\{\s*$")),
        ("case", re.compile(r"^\s*case\s+([A-Za-z_]\w*)")),
    ],
    "objc": [
        ("type", re.compile(r"^\s*@(interface|implementation|protocol)\s+([A-Za-z_]\w*)")),
        ("func", re.compile(r"^\s*[-+]\s*\([^)]*\)\s*([A-Za-z_]\w*)(.*)$")),
        ("func", re.compile(r"^\s*(?:static\s+)?[\w\s\*]+?\b([A-Za-z_]\w*)\s*\(([^)]*)\)\s*\{?\s*$")),
    ],
    "kotlin": [
        ("type", re.compile(r"^\s*" + MOD + r"(class|interface|object|enum class)\s+([A-Za-z_]\w*)")),
        ("func", re.compile(r"^\s*" + MOD + r"fun\s+(?:<[^>]*>\s*)?(?:[\w.]+\.)?([A-Za-z_]\w*)\s*\(([^)]*)\)?")),
    ],
    "java": [
        ("type", re.compile(r"^\s*" + MOD + r"(class|interface|enum|record)\s+([A-Za-z_]\w*)")),
        ("func", re.compile(r"^\s*" + MOD + r"(?:<[^>]*>\s*)?[\w<>\[\],.? ]+\s+([A-Za-z_]\w*)\s*\(([^)]*)\)?\s*(?:throws [\w., ]+)?\s*\{?\s*$")),
    ],
    "csharp": [
        ("type", re.compile(r"^\s*" + MOD + r"(class|interface|struct|enum|record)\s+([A-Za-z_]\w*)")),
        ("func", re.compile(r"^\s*" + MOD + r"[\w<>\[\],.? ]+\s+([A-Za-z_]\w*)\s*\(([^)]*)\)?\s*\{?\s*$")),
    ],
    "go": [
        ("func", re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*\(([^)]*)\)?")),
        ("type", re.compile(r"^\s*type\s+([A-Za-z_]\w*)\s+(struct|interface)")),
    ],
    "js": [
        ("type", re.compile(r"^\s*" + MOD + r"(class|interface)\s+([A-Za-z_]\w*)")),
        ("func", re.compile(r"^\s*" + MOD + r"function\s*\*?\s*([A-Za-z_]\w*)\s*\(([^)]*)\)?")),
        ("func", re.compile(r"^\s*(?:const|let|var)\s+([A-Za-z_]\w*)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>")),
        ("func", re.compile(r"^\s*" + MOD + r"(?!if\b|for\b|while\b|switch\b|catch\b|return\b)([A-Za-z_]\w*)\s*\(([^)]*)\)\s*(?::\s*[^{]+)?\{\s*$")),
    ],
}
KEYWORDS = {"if", "for", "while", "switch", "catch", "guard", "return", "else", "do", "repeat", "defer", "when", "try"}


@dataclass
class Symbol:
    kind: str
    name: str
    key: str
    start: int
    end: int
    container: str = ""
    children: list = field(default_factory=list)

    @property
    def qual(self):
        return f"{self.container}.{self.key}" if self.container else self.key

    def as_dict(self):
        return {"kind": self.kind, "name": self.name, "key": self.key, "qual": self.qual, "start": self.start, "end": self.end}


def lang_of(path):
    for ext, l in LANG_BY_EXT.items():
        if path.lower().endswith(ext):
            return l
    return None


def _labels(params, lang):
    """Swift: argument labels → name(_:with:) ; others: parameter count."""
    if params is None:
        return ""
    params = params.strip()
    if not params:
        return "()"
    if lang == "swift":
        labs = []
        for p in re.split(r",(?![^<(\[]*[>)\]])", params):
            p = p.strip()
            if not p or ":" not in p:
                continue
            head = p.split(":")[0].split()
            labs.append((head[0] if head else "_") + ":")
        return "(" + "".join(labs) + ")"
    if lang == "objc":
        return "(" + "".join(re.findall(r"(\w+:)", params)) + ")"
    return f"({len([p for p in params.split(',') if p.strip()])})"


def _strip(line, state):
    """Remove strings and comments for brace counting. state: in_block_comment flag (list of one bool)."""
    out, i, n = [], 0, len(line)
    while i < n:
        if state[0]:
            j = line.find("*/", i)
            if j < 0:
                return "".join(out)
            state[0] = False; i = j + 2; continue
        c = line[i]
        if line.startswith("//", i):
            break
        if line.startswith("/*", i):
            state[0] = True; i += 2; continue
        if c in "\"'`":
            q = c; i += 1
            while i < n and line[i] != q:
                i += 2 if line[i] == "\\" else 1
            i += 1; continue
        out.append(c); i += 1
    return "".join(out)


def index(text, lang):
    if not text or lang not in PATTERNS:
        return []
    lines = text.splitlines()
    clean, st = [], [False]
    for l in lines:
        clean.append(_strip(l, st))
    syms = []
    for i, raw in enumerate(lines):
        if not clean[i].strip():
            continue
        for kind, rx in PATTERNS[lang]:
            m = rx.match(raw)
            if not m:
                continue
            g = [x for x in m.groups()]
            if kind == "type":
                tkind, name = (g[0], g[1]) if len(g) > 1 else ("type", g[0])
                if lang == "go":
                    name, tkind = g[0], g[1]
                key = name if tkind != "extension" else f"extension {name}"
                sym = Symbol("type", name.split(".")[-1] if tkind != "extension" else name, key, i, i)
            elif kind == "init":
                sym = Symbol("func", g[0], g[0] + _labels(g[1] if len(g) > 1 else "", lang), i, i)
            elif kind in ("var", "case"):
                if kind == "case" and lang != "swift":
                    continue
                sym = Symbol(kind, g[0], g[0], i, i)
            else:
                name = g[0]
                if name in KEYWORDS:
                    continue
                params = g[1] if len(g) > 1 else ""
                if lang == "objc" and raw.lstrip()[:1] in "-+":
                    sel = "".join(re.findall(r"(\w+:)", name + (g[1] or ""))) or name
                    sym = Symbol("func", name, sel, i, i)
                else:
                    sym = Symbol("func", name, name + _labels(params, lang), i, i)
            # where does the signature end? (balanced parentheses, may span lines)
            k, pd, seen_paren = i, 0, False
            while k < len(lines) and k < i + 30:
                for ch in clean[k]:
                    if ch == "(":
                        pd += 1; seen_paren = True
                    elif ch == ")":
                        pd -= 1
                if pd <= 0 and (seen_paren or k == i):
                    break
                k += 1
            has_body = "{" in clean[k] or (k + 1 < len(lines) and clean[k + 1].lstrip().startswith("{")) or \
                       (k + 1 < len(lines) and re.match(r"^\s*(->|throws|async|where|:)", clean[k + 1]) is not None
                        and any("{" in clean[x] for x in range(k + 1, min(k + 4, len(lines)))))
            if sym.kind == "func" and not (lang == "objc" and raw.lstrip()[:1] in "-+"):
                sig = " ".join(clean[i:k + 1])
                a = sig.find("(", sig.find(sym.name) + len(sym.name) if sym.name in sig else 0)
                if a >= 0:
                    d_, b = 0, a
                    while b < len(sig):
                        d_ += {"(": 1, ")": -1}.get(sig[b], 0)
                        if d_ == 0:
                            break
                        b += 1
                    sym.key = sym.name + _labels(sig[a + 1:b], lang)
            if lang == "objc" and kind == "type":
                j = i
                while j < len(lines) and not lines[j].strip().startswith("@end"):
                    j += 1
                sym.end = min(j, len(lines) - 1)
            elif not has_body:
                sym.end = k
            else:
                depth, opened, j = 0, False, i
                while j < len(lines) and j < i + 5000:
                    for ch in clean[j]:
                        if ch == "{":
                            depth += 1; opened = True
                        elif ch == "}":
                            depth -= 1
                    if opened and depth <= 0:
                        break
                    j += 1
                sym.end = min(j, len(lines) - 1)
            syms.append(sym)
            break
    # containers (innermost type that encloses a symbol)
    types = sorted([s for s in syms if s.kind == "type"], key=lambda s: (s.start, -s.end))
    for s in syms:
        best = None
        for t in types:
            if t is s:
                continue
            if t.start <= s.start and s.end <= t.end and (t.start, t.end) != (s.start, s.end):
                if best is None or (t.end - t.start) < (best.end - best.start):
                    best = t
        if best:
            s.container = best.name if not best.key.startswith("extension ") else best.key.split(" ", 1)[1]
    return syms


def enclosing(symbols, line0, line1=None, prefer=("func", "var", "case", "type")):
    line1 = line0 if line1 is None else line1
    hits = [s for s in symbols if s.start <= line0 and line1 <= s.end]
    if not hits:
        return None
    hits.sort(key=lambda s: (prefer.index(s.kind) if s.kind in prefer else 9, s.end - s.start))
    return hits[0]


def find(symbols, ref):
    """Find a symbol by qual, then key within same container name, then key, then bare name (unique only)."""
    for s in symbols:
        if s.qual == ref.qual and s.kind == ref.kind:
            return s
    for s in symbols:
        if s.key == ref.key and s.kind == ref.kind and (s.container.split(".")[-1] == ref.container.split(".")[-1]):
            return s
    same_key = [s for s in symbols if s.key == ref.key and s.kind == ref.kind]
    if len(same_key) == 1:
        return same_key[0]
    same_name = [s for s in symbols if s.name == ref.name and s.kind == ref.kind]
    if len(same_name) == 1:
        return same_name[0]
    return None


def body(text, sym):
    return text.splitlines()[sym.start:sym.end + 1]


if __name__ == "__main__":
    t = open(sys.argv[1], encoding="utf-8", errors="replace").read()
    for s in index(t, lang_of(sys.argv[1])):
        print(f"{s.start + 1:5d}-{s.end + 1:<5d} {s.kind:5s} {s.qual}")
