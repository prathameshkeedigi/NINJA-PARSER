"""Negative control: does the proof catch a WRONG parser?

A check that can never fail proves nothing. This script makes 5 copies of
ninja_parse.py, each with one deliberate bug, runs the same 4 checks with each
broken copy, and records which checks catch the bug. ninja_parse.py itself is
not changed. Output: results\\NEGATIVE_CONTROL.md

usage (from the Build_ninja_proof folder):  python tools\\negative_control.py
"""
import importlib.util
import os
import sys
import tempfile

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import run_proof  # noqa: E402

# (name, what the bug does, exact original text, broken text)
BUGS = [
    ("B1 undefined variable kept",
     "an undefined variable becomes the text $NAME instead of empty text",
     'return ""                       # manual: undefined variable -> empty string',
     'return "$" + name'),
    ("B2 escaped space not understood",
     "the escape '$ ' (a space inside a path) is not recognised",
     'if n in ("$", " ", ":"):',
     'if n in ("$", ":"):'),
    ("B3 implicit outputs dropped",
     "outputs after '|' on a build line are thrown away",
     "edge.outs, edge.implicit_outs = ev(outs), ev(imp_outs)",
     "edge.outs, edge.implicit_outs = ev(outs), []"),
    ("B4 order-only inputs dropped",
     "inputs after '||' on a build line are thrown away",
     "edge.order_only = ev(ins), ev(imp_ins), ev(order)",
     "edge.order_only = ev(ins), ev(imp_ins), []"),
    ("B5 waiting arrows from explicit inputs only",
     "a task waits only for producers of its explicit inputs, not of its | and || inputs",
     "deps = [sorted({producer[canon(x)] for x in e.all_inputs() if canon(x) in producer})",
     "deps = [sorted({producer[canon(x)] for x in e.ins if canon(x) in producer})"),
]
PROJECTS = ["01_basic_exe", "03_shared_lib", "05_generated_header", "16_spaces_in_paths"]


def broken_module(src_text, n):
    path = os.path.join(tempfile.mkdtemp(prefix="broken_parser_"), f"ninja_parse_bug{n}.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(src_text)
    spec = importlib.util.spec_from_file_location(f"ninja_parse_bug{n}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    original = open(os.path.join(TOOLS, "ninja_parse.py"), encoding="utf-8").read()
    out = tempfile.mkdtemp(prefix="negative_control_")
    run_proof.BUILDS = os.path.join(out, "builds")      # never touches the real results
    run_proof.RESULTS = os.path.join(out, "results")
    lines = ["# Negative control: a deliberately broken parser must FAIL the checks", "",
             "Each row uses a copy of `tools/ninja_parse.py` with ONE bug put in on purpose. "
             "`FAIL` or `ERROR` in a cell means the proof caught that bug in that project. "
             "`PASS` means that project does not contain the build.ninja feature the bug breaks.", "",
             "| Bug | What the bug does | " + " | ".join(PROJECTS) + " |",
             "|---|---|" + "---|" * len(PROJECTS)]
    for n, (name, what, old, new) in enumerate(BUGS, 1):
        assert original.count(old) == 1, f"text for {name} not found exactly once"
        mod = broken_module(original.replace(old, new), n)
        run_proof.load, run_proof.canon, run_proof.NinjaError = mod.load, mod.canon, mod.NinjaError
        cells = []
        for proj in PROJECTS:
            try:
                r = run_proof.prove(proj)
            except Exception as ex:                       # a crash also means "caught"
                r = {"error": f"{type(ex).__name__}: {ex}"}
            if "error" in r:
                cell = "ERROR (" + r["error"].splitlines()[0][:60].replace("|", "/") + ")"
            else:
                failed = [k for k in ("c1", "c2", "c3", "c4") if r.get(k) is not True]
                cell = ("FAIL check " + ",".join(k[1] for k in failed)) if failed else "PASS"
            cells.append(cell)
            print(f"{name:45} {proj:22} {cell}")
        lines.append(f"| {name} | {what.replace('|', chr(92) + '|')} | " + " | ".join(cells) + " |")
    caught = sum(any(c != "PASS" for c in row.split(" | ")[2:]) for row in lines[6:])
    lines += ["", f"**{caught} of {len(BUGS)} deliberate bugs were caught by at least one project.**"]
    with open(os.path.join(TOOLS, "..", "results", "NEGATIVE_CONTROL.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\n{caught} of {len(BUGS)} bugs caught; see results\\NEGATIVE_CONTROL.md")


if __name__ == "__main__":
    main()
