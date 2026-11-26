#!/usr/bin/env python3
"""
pbx_targets.py — which Xcode targets include a file (read-only, works on macOS and Linux).

Usage:
  pbx_targets.py <path/to/project.pbxproj> --list-targets
  pbx_targets.py <path/to/project.pbxproj> <file name or relative path> [...]
  pbx_targets.py <pbxproj> --ref <git ref> --repo <repo> <files...>   # read the project file from a branch
  pbx_targets.py <pbxproj> --duplicates [--ref <ref> --repo <repo>]    # files listed twice in one build phase
                 (run on the merged file and on the target branch: entries only in the merged result came from the merge)

For each file prints JSON: matching file references, their group path, and for every target the
build phase it is in (Sources / Resources / Frameworks / CopyFiles). Also reports Xcode 16
synchronized folders (PBXFileSystemSynchronizedRootGroup) that would include the file automatically.

Use it on the SOURCE branch's project to learn where a new/moved file belongs, then make the
TARGET project match (same target names; ask when a target does not exist in target).
"""
import json, os, subprocess, sys


class P:
    """Minimal OpenStep (old-style) plist parser — enough for project.pbxproj."""
    def __init__(self, s):
        self.s, self.i = s, 0

    def ws(self):
        s = self.s
        while self.i < len(s):
            c = s[self.i]
            if c in " \t\r\n":
                self.i += 1
            elif s.startswith("//", self.i):
                self.i = s.find("\n", self.i) + 1 or len(s)
            elif s.startswith("/*", self.i):
                self.i = s.find("*/", self.i) + 2
            else:
                break

    def val(self):
        self.ws(); c = self.s[self.i]
        if c == "{":
            self.i += 1; d = {}
            while True:
                self.ws()
                if self.s[self.i] == "}":
                    self.i += 1; return d
                k = self.val(); self.ws(); assert self.s[self.i] == "=", self.s[self.i - 20:self.i + 20]; self.i += 1
                d[k] = self.val(); self.ws()
                if self.s[self.i] == ";":
                    self.i += 1
        if c == "(":
            self.i += 1; a = []
            while True:
                self.ws()
                if self.s[self.i] == ")":
                    self.i += 1; return a
                a.append(self.val()); self.ws()
                if self.s[self.i] == ",":
                    self.i += 1
        if c == '"':
            self.i += 1; out = []
            while self.s[self.i] != '"':
                if self.s[self.i] == "\\":
                    self.i += 1
                    out.append({"n": "\n", "t": "\t"}.get(self.s[self.i], self.s[self.i]))
                else:
                    out.append(self.s[self.i])
                self.i += 1
            self.i += 1; return "".join(out)
        j = self.i
        while self.i < len(self.s) and (self.s[self.i].isalnum() or self.s[self.i] in "_$/:.-+"):
            self.i += 1
        return self.s[j:self.i]


def load(path, ref=None, repo=None):
    if ref:
        txt = subprocess.run(["git", "-C", repo or ".", "show", f"{ref}:{path}"], capture_output=True, text=True, check=True).stdout
    else:
        txt = open(path, encoding="utf-8").read()
    if txt.startswith("// !$*UTF8*$!"):
        txt = txt.split("\n", 1)[1]
    return P(txt).val()


def memberships(root, basename):
    """{target name: phase} for every PBXFileReference named `basename` (first match per target)."""
    objs = root["objects"]
    targets = {k: v for k, v in objs.items() if v.get("isa") in ("PBXNativeTarget", "PBXAggregateTarget", "PBXLegacyTarget")}
    phase_of_bf, target_of_phase = {}, {}
    for k, v in objs.items():
        if v.get("isa", "").endswith("BuildPhase"):
            for bf in v.get("files", []) or []:
                phase_of_bf[bf] = (k, v["isa"].replace("PBX", "").replace("BuildPhase", ""))
    for tk, tv in targets.items():
        for ph in tv.get("buildPhases", []) or []:
            target_of_phase[ph] = tv.get("name")
    refs = {k for k, v in objs.items() if v.get("isa") == "PBXFileReference" and
            (os.path.basename(v.get("path", "")) == basename or v.get("name") == basename)}
    out = {}
    for k, v in objs.items():
        if v.get("isa") == "PBXBuildFile" and v.get("fileRef") in refs and k in phase_of_bf:
            ph, kind = phase_of_bf[k]
            out.setdefault(target_of_phase.get(ph, "?"), kind)
    return out


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    pbx = args.pop(0)
    ref = repo = None
    if "--ref" in args:
        k = args.index("--ref"); ref = args[k + 1]; del args[k:k + 2]
    if "--repo" in args:
        k = args.index("--repo"); repo = args[k + 1]; del args[k:k + 2]
    root = load(pbx, ref, repo)
    objs = root["objects"]
    targets = {k: v for k, v in objs.items() if v.get("isa") in ("PBXNativeTarget", "PBXAggregateTarget", "PBXLegacyTarget")}
    if "--duplicates" in args:
        # same file referenced twice in one build phase → Xcode warns "Skipping duplicate build file"
        phase_kind, target_of = {}, {}
        for tk, tv in targets.items():
            for ph in tv.get("buildPhases", []) or []:
                target_of[ph] = tv.get("name")
        res = []
        for k, v in objs.items():
            if v.get("isa", "").endswith("BuildPhase"):
                seen = {}
                for bf in v.get("files", []) or []:
                    fr = objs.get(bf, {}).get("fileRef") or objs.get(bf, {}).get("productRef")
                    if fr:
                        seen.setdefault(fr, []).append(bf)
                for fr, bfs in seen.items():
                    if len(bfs) > 1:
                        o = objs.get(fr, {})
                        res.append({"target": target_of.get(k, "?"), "phase": v["isa"].replace("PBX", ""),
                                    "file": o.get("path") or o.get("name") or o.get("productName") or fr, "count": len(bfs)})
        print(json.dumps(sorted(res, key=lambda r: (r["target"], r["file"])), indent=1))
        return
    if "--list-targets" in args:
        print(json.dumps([{"name": v.get("name"), "productType": v.get("productType"), "id": k} for k, v in targets.items()], indent=1))
        return

    parent = {}
    for k, v in objs.items():
        for c in v.get("children", []) or []:
            parent[c] = k

    def group_path(oid):
        parts, cur = [], oid
        while cur in parent:
            cur = parent[cur]
            o = objs[cur]
            if o.get("path") or o.get("name"):
                parts.append(o.get("path") or o.get("name"))
        return "/".join(reversed(parts))

    phase_of_bf, phase_kind = {}, {}
    for k, v in objs.items():
        if v.get("isa", "").endswith("BuildPhase"):
            phase_kind[k] = v["isa"].replace("PBX", "").replace("BuildPhase", "") + (f" ({v.get('name')})" if v.get("name") else "")
            for bf in v.get("files", []) or []:
                phase_of_bf[bf] = k
    target_of_phase = {}
    for tk, tv in targets.items():
        for ph in tv.get("buildPhases", []) or []:
            target_of_phase[ph] = tv.get("name")
    sync_groups = {k: v for k, v in objs.items() if v.get("isa") == "PBXFileSystemSynchronizedRootGroup"}
    sync_targets = {}
    for tk, tv in targets.items():
        for g in tv.get("fileSystemSynchronizedGroups", []) or []:
            sync_targets.setdefault(g, []).append(tv.get("name"))

    out = []
    for q in args:
        qb = os.path.basename(q)
        refs = [k for k, v in objs.items() if v.get("isa") == "PBXFileReference" and
                (os.path.basename(v.get("path", "")) == qb or v.get("name") == qb)]
        rec = {"query": q, "references": []}
        for r in refs:
            gp = group_path(r)
            full = (gp + "/" if gp else "") + objs[r].get("path", "")
            mem = []
            for k, v in objs.items():
                if v.get("isa") == "PBXBuildFile" and v.get("fileRef") == r:
                    ph = phase_of_bf.get(k)
                    mem.append({"target": target_of_phase.get(ph, "?"), "phase": phase_kind.get(ph, "?")})
            rec["references"].append({"id": r, "group_path": full, "sourceTree": objs[r].get("sourceTree"), "memberships": mem,
                                      "path_match": q in full or full.endswith(q)})
        rec["synchronized_folders"] = [{"folder": g.get("path"), "targets": sync_targets.get(k, [])}
                                       for k, g in sync_groups.items() if g.get("path") and (q.startswith(g["path"] + "/") or ("/" + g["path"] + "/") in "/" + q)]
        if not rec["references"] and not rec["synchronized_folders"]:
            rec["note"] = "not referenced in this project (not compiled by any target, or lives in a package)"
        out.append(rec)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
