"""Proof that our build.ninja parser understands build.ninja exactly like Ninja does.

usage (from the Build_ninja_proof folder):
    python tools\\run_proof.py              all projects
    python tools\\run_proof.py 05_generated_header 20_zlib   only these

For every project in projects\\ it does:
  configure  CMake writes two fresh build folders: builds\\<p>\\by_ninja and builds\\<p>\\by_our_parser
  check 1    for EVERY file node: our text == `ninja -t query <node>`
             (which rule makes it, its inputs with | and || markers, who uses it)
  check 2    for EVERY build step: our command text == `ninja -t commands <output>`
             (fully expanded command lines, same order)
  check 3    our Kahn order is a valid order: every task comes after all tasks it waits for
  check 4    build by_ninja with real Ninja; build by_our_parser by running ONLY the commands
             our parser produced, one by one in our order (Ninja is not used); run the
             programs from both folders and compare what they print
Evidence files go to results\\<p>\\, the table to results\\SUMMARY.md.
"""
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ninja_parse import load, canon, NinjaError  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECTS, BUILDS, RESULTS = (os.path.join(HERE, d) for d in ("projects", "builds", "results"))
FALLBACK = r"C:\Users\Asus\AppData\Roaming\Python\Python313\Scripts"


def tool(name):
    return shutil.which(name) or os.path.join(FALLBACK, name + ".exe")


CMAKE, NINJA = tool("cmake"), tool("ninja")


def run(args, cwd=None, timeout=600):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          errors="replace", timeout=timeout)


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def configure(src, bdir, extra):
    shutil.rmtree(bdir, ignore_errors=True)
    r = run([CMAKE, "-G", "Ninja", "-S", src, "-B", bdir,
             "-DCMAKE_MAKE_PROGRAM=" + NINJA] + extra)
    return r.returncode == 0, r.stdout + r.stderr


# ------------------------------------------------ what our parser answers ---
def our_query(p, g, consumers, x):
    """Same layout as `ninja -t query`."""
    s = f"{x}:\n"
    if canon(x) in g["producer"]:
        e = p.edges[g["producer"][canon(x)]]
        s += f"  input: {e.rule['name']}\n"
        s += "".join(f"    {i}\n" for i in e.ins)
        s += "".join(f"    | {i}\n" for i in e.implicit_ins)
        s += "".join(f"    || {i}\n" for i in e.order_only)
    s += "  outputs:\n"
    for e in consumers.get(canon(x), []):
        s += "".join(f"    {o}\n" for o in e.all_outputs())
    return s


def our_commands(p, g, targets):
    """Same walk as `ninja -t commands t1 t2 ...`: inputs first, each step once."""
    out, done = [], set()

    def visit(i):
        if i in done:
            return
        done.add(i)
        for x in p.edges[i].all_inputs():
            if canon(x) in g["producer"]:
                visit(g["producer"][canon(x)])
        if not p.edges[i].is_phony():
            out.append(p.edges[i].command())
    for t in targets:
        visit(g["producer"][canon(t)])
    return out


# ------------------------------------------------------------- the checks ---
def checks_1_2_3(bdir, res):
    p, g = load(os.path.join(bdir, "build.ninja"))
    nin = lambda args: run([NINJA, "-C", bdir] + args)

    nodes, seen = [], set()
    for e in p.edges:
        for x in e.all_outputs() + e.all_inputs():
            if canon(x) not in seen:
                seen.add(canon(x))
                nodes.append(x)
    consumers = {}
    for e in p.edges:
        for x in e.all_inputs():
            consumers.setdefault(canon(x), []).append(e)

    theirs, ours = [], []
    for k in range(0, len(nodes), 15):          # batches keep the command line short
        batch = nodes[k:k + 15]
        r = nin(["-t", "query"] + batch)
        if r.returncode:
            raise RuntimeError("ninja -t query failed: " + r.stderr)
        theirs.append(r.stdout)
        ours.append("".join(our_query(p, g, consumers, x) for x in batch))
    write(os.path.join(res, "check1_ninja_query.txt"), "".join(theirs))
    write(os.path.join(res, "check1_parser_query.txt"), "".join(ours))
    c1 = "".join(theirs) == "".join(ours)

    firsts = [e.all_outputs()[0] for e in p.edges]
    theirs, ours = [], []
    for k in range(0, len(firsts), 10):
        batch = firsts[k:k + 10]
        r = nin(["-t", "commands"] + batch)
        if r.returncode:
            raise RuntimeError("ninja -t commands failed: " + r.stderr)
        theirs += r.stdout.splitlines()
        ours += our_commands(p, g, batch)
    write(os.path.join(res, "check2_ninja_commands.txt"), "\n".join(theirs) + "\n")
    write(os.path.join(res, "check2_parser_commands.txt"), "\n".join(ours) + "\n")
    c2 = theirs == ours

    pos = {i: n for n, i in enumerate(g["order"])}
    bad = [(i, j) for i in g["reach"] for j in g["deps"][i] if pos[j] > pos[i]]
    lines = [f"{n}. [{p.edges[i].rule['name']}] {p.edges[i].outs[0]}   waits for: "
             f"{[p.edges[j].outs[0] for j in g['deps'][i]] or '-'}"
             for n, i in enumerate(g["order"], 1)]
    write(os.path.join(res, "check3_parser_order.txt"),
          "Order computed by our parser (Kahn's algorithm), tasks needed by the default target:\n"
          + "\n".join(lines) + f"\n\nviolations (a task placed before a task it waits for): {len(bad)}\n")
    return dict(statements=len(p.edges), nodes=len(nodes), commands=len(theirs),
                tasks=len(g["order"]), c1=c1, c2=c2, c3=not bad)


def run_programs(bdir, programs):
    out = []
    for prog in programs:
        exe, *args = prog.split()
        r = run([os.path.join(bdir, exe)] + args, cwd=bdir, timeout=60)
        out.append(f"$ {prog}   (exit code {r.returncode})\n{r.stdout}{r.stderr}")
    return "".join(out)


def build_with_our_parser(bdir, log):
    """Run only the commands our parser produced, in our order. No Ninja."""
    p, g = load(os.path.join(bdir, "build.ninja"))
    ran = 0
    for i in g["order"]:
        e = p.edges[i]
        if e.is_phony():
            continue
        for o in e.all_outputs():                  # Ninja makes output folders too
            d = os.path.dirname(os.path.join(bdir, o))
            if d:
                os.makedirs(d, exist_ok=True)
        rsp = e.var("rspfile")
        if rsp:                                    # Ninja writes the @file before running
            write(os.path.join(bdir, rsp), e.var("rspfile_content"))
        cmd = e.command()
        try:
            r = subprocess.run(cmd, cwd=bdir, capture_output=True, text=True, errors="replace")
        except OSError as ex:                      # the program could not even start
            log.append(f"[{ran + 1}] {cmd}\nCOULD NOT START: {ex}")
            return False, ran
        log.append(f"[{ran + 1}] {cmd}\n{r.stdout}{r.stderr}")
        if r.returncode:
            return False, ran
        ran += 1
    return True, ran


def check_4(src, b_ninja, b_ours, programs, res):
    r = run([NINJA, "-C", b_ninja])
    write(os.path.join(res, "check4_build_log_ninja.txt"), r.stdout + r.stderr)
    if r.returncode:
        return dict(c4=False, note="Ninja build failed")
    log = []
    ok, ran = build_with_our_parser(b_ours, log)
    write(os.path.join(res, "check4_build_log_our_parser.txt"), "\n".join(log))
    if not ok:
        return dict(c4=False, note="build from our parser's commands failed", ran=ran)
    a, b = run_programs(b_ninja, programs), run_programs(b_ours, programs)
    write(os.path.join(res, "check4_program_output_ninja.txt"), a)
    write(os.path.join(res, "check4_program_output_our_parser.txt"), b)
    return dict(c4=(a == b and "exit code 0" in a), ran=ran, output=a)


def prove(name):
    src = os.path.join(PROJECTS, name)
    meta = json.load(open(os.path.join(src, "proof.json"), encoding="utf-8"))
    res = os.path.join(RESULTS, name)
    shutil.rmtree(res, ignore_errors=True)
    os.makedirs(res)
    b_ninja = os.path.join(BUILDS, name, "by_ninja")
    b_ours = os.path.join(BUILDS, name, "by_our_parser")
    row = dict(name=name, tests=meta["tests"],
               c_files=sum(f.endswith(".c") for _, _, fs in os.walk(src) for f in fs))
    t0 = time.time()
    try:
        for b in (b_ninja, b_ours):
            ok, text = configure(src, b, meta.get("cmake_args", []))
            write(os.path.join(res, "configure_" + os.path.basename(b) + ".log"), text)
            if not ok:
                raise RuntimeError("cmake configure failed")
        row.update(checks_1_2_3(b_ninja, res))
        row.update(check_4(src, b_ninja, b_ours, meta["run"], res))
    except (NinjaError, RuntimeError) as ex:
        row["error"] = str(ex)
    row["seconds"] = round(time.time() - t0, 1)
    write(os.path.join(res, "result.json"), json.dumps(row, indent=2))
    return row


def mark(v):
    return "PASS" if v is True else ("FAIL" if v is False else "-")


def summary(rows):
    ver = lambda exe: run([exe, "--version"]).stdout.splitlines()[0]
    gcc = shutil.which("gcc") or r"C:\msys64\ucrt64\bin\gcc.exe"
    t = ["# Build.ninja parser proof: results", "",
         f"Run on {time.strftime('%Y-%m-%d %H:%M')} with {ver(CMAKE)}, "
         f"Ninja {ver(NINJA)}, {ver(gcc)}.", "",
         "| # | Project | .c files in folder | build statements | nodes | commands | tasks run | "
         "check 1 query | check 2 commands | check 3 order | check 4 build+run |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for n, r in enumerate(rows, 1):
        t.append(f"| {n} | {r['name']} | {r['c_files']} | {r.get('statements', '-')} | "
                 f"{r.get('nodes', '-')} | {r.get('commands', '-')} | {r.get('ran', '-')} | "
                 f"{mark(r.get('c1'))} | {mark(r.get('c2'))} | {mark(r.get('c3'))} | "
                 f"{mark(r.get('c4'))} |")
    passed = sum(all(r.get(k) is True for k in ("c1", "c2", "c3", "c4")) for r in rows)
    t += ["", f"**{passed} of {len(rows)} projects pass all four checks.**", ""]
    problems = [r for r in rows if "error" in r or r.get("note")]
    for r in problems:
        t.append(f"- {r['name']}: {r.get('error') or r.get('note')}")
    t += ["", "## What each project tests", ""]
    t += [f"- **{r['name']}**: {r['tests']}" for r in rows]
    write(os.path.join(RESULTS, "SUMMARY.md"), "\n".join(t) + "\n")
    return passed


if __name__ == "__main__":
    names = sys.argv[1:] or sorted(d for d in os.listdir(PROJECTS)
                                   if os.path.isfile(os.path.join(PROJECTS, d, "proof.json")))
    rows = []
    for name in names:
        r = prove(name)
        rows.append(r)
        print(f"{name:30} q={mark(r.get('c1'))} cmd={mark(r.get('c2'))} order={mark(r.get('c3'))} "
              f"build+run={mark(r.get('c4'))}  ({r['seconds']}s) {r.get('error', '') or r.get('note', '')}")
    if len(names) == len(os.listdir(PROJECTS)) or not sys.argv[1:]:
        print(f"\n{summary(rows)} of {len(rows)} pass all checks; see results\\SUMMARY.md")
