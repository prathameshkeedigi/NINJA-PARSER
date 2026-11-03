"""Proof-of-concept: parse a build.ninja file and turn it into a DAG.

Written from the Ninja manual (https://ninja-build.org/manual.html, "Ninja file
reference" section). Not production code; it exists to answer two questions:
  1. Can build.ninja be parsed?   2. Can the result be turned into a DAG?
"""
import os
import re
import sys
from collections import deque

IDENT = re.compile(r"[A-Za-z0-9_.\-]+")       # names in declarations and ${...}
SIMPLE_VAR = re.compile(r"[A-Za-z0-9_\-]+")   # names in $name (no dot)


class NinjaError(Exception):
    pass


# ---------------------------------------------------------------- scopes ---
class Scope:
    """File-level variables and rules. include shares a scope, subninja nests one."""

    def __init__(self, parent=None):
        self.vars, self.rules, self.parent = {}, {}, parent

    def lookup(self, name):
        s = self
        while s:
            if name in s.vars:
                return s.vars[name]
            s = s.parent
        return ""                       # manual: undefined variable -> empty string

    def rule(self, name):
        s = self
        while s:
            if name in s.rules:
                return s.rules[name]
            s = s.parent
        return None


def evaluate(parts, lookup):
    """parts = list of ('lit', text) / ('var', name)."""
    return "".join(t if k == "lit" else lookup(t) for k, t in parts)


# ----------------------------------------------------------------- lexer ---
class Lexer:
    def __init__(self, text, filename):
        self.t, self.p, self.fn = text, 0, filename

    def error(self, msg):
        line = self.t.count("\n", 0, self.p) + 1
        raise NinjaError(f"{self.fn}:{line}: {msg}")

    def peek(self, n=0):
        i = self.p + n
        return self.t[i] if i < len(self.t) else ""

    def at_line_continuation(self):
        return self.t.startswith("$\n", self.p) or self.t.startswith("$\r\n", self.p)

    def skip_continuation(self):
        self.p += 2 if self.peek(1) == "\n" else 3
        while self.peek() == " ":
            self.p += 1

    def skip_spaces(self):
        while True:
            if self.peek() == " ":
                self.p += 1
            elif self.at_line_continuation():
                self.skip_continuation()
            else:
                return

    def at_newline(self):
        return self.peek() in ("\n", "") or self.t.startswith("\r\n", self.p)

    def expect_newline(self):
        self.skip_spaces()
        if not self.at_newline():
            self.error(f"expected newline, got {self.t[self.p:self.p + 20]!r}")
        self.p += 0 if self.peek() == "" else (1 if self.peek() == "\n" else 2)

    def ident(self):
        m = IDENT.match(self.t, self.p)
        if not m:
            self.error("expected a name")
        self.p = m.end()
        return m.group()

    def eval_string(self, path):
        """Read a value (path=False: to end of line) or one path (path=True:
        stops at unescaped space, ':' or '|'). Returns a list of parts."""
        parts, lit = [], []
        while True:
            c = self.peek()
            if c == "" or c == "\n" or self.t.startswith("\r\n", self.p):
                break
            if path and c in " :|":
                break
            if c != "$":
                lit.append(c)
                self.p += 1
                continue
            n = self.peek(1)
            if n in ("$", " ", ":"):                       # $$  "$ "  $:
                lit.append(n)
                self.p += 2
            elif self.at_line_continuation():              # $ + newline
                self.skip_continuation()
            elif n == "{":                                 # ${name}
                end = self.t.find("}", self.p)
                if end < 0 or not IDENT.fullmatch(self.t[self.p + 2:end]):
                    self.error("bad ${...}")
                parts.append(("lit", "".join(lit)))
                lit = []
                parts.append(("var", self.t[self.p + 2:end]))
                self.p = end + 1
            else:                                          # $name
                m = SIMPLE_VAR.match(self.t, self.p + 1)
                if not m:
                    self.error(f"bad $-escape: {self.t[self.p:self.p + 2]!r}")
                parts.append(("lit", "".join(lit)))
                lit = []
                parts.append(("var", m.group()))
                self.p = m.end()
        parts.append(("lit", "".join(lit)))
        if path:
            self.skip_spaces()
        return parts

    def next_line_indented(self):
        """Skip blank-free comment lines; report whether next line is indented."""
        while True:
            q = self.p
            while q < len(self.t) and self.t[q] == " ":
                q += 1
            if q < len(self.t) and self.t[q] == "#":       # comment line
                nl = self.t.find("\n", q)
                self.p = len(self.t) if nl < 0 else nl + 1
                continue
            return q > self.p and not (self.t[q:q + 1] in ("\n", "") or self.t.startswith("\r\n", q))


# ----------------------------------------------------------------- graph ---
class Edge:
    def __init__(self, rule, scope):
        self.rule, self.scope = rule, scope
        self.outs, self.implicit_outs = [], []
        self.ins, self.implicit_ins, self.order_only = [], [], []
        self.bindings = {}

    def all_outputs(self):
        return self.outs + self.implicit_outs

    def all_inputs(self):
        return self.ins + self.implicit_ins + self.order_only

    def var(self, name, depth=0):
        """Manual's lookup order: $in/$out, build block, rule block, file."""
        if depth > 50:
            raise NinjaError(f"variable cycle at {name}")
        if name == "in":
            return " ".join(shell_quote(p) for p in self.ins)
        if name == "in_newline":
            return "\n".join(shell_quote(p) for p in self.ins)
        if name == "out":
            return " ".join(shell_quote(p) for p in self.outs)
        if name in self.bindings:
            return self.bindings[name]
        if name in self.rule["vars"]:
            return evaluate(self.rule["vars"][name], lambda v: self.var(v, depth + 1))
        return self.scope.lookup(name)

    def command(self):
        return self.var("command")

    def is_phony(self):
        return self.rule["name"] == "phony"


def shell_quote(p):
    # Windows: quote only paths containing a space or a quote (simplified).
    return f'"{p}"' if (" " in p or '"' in p) else p


def canon(p):
    """Canonical key used to match one edge's output to another edge's input:
    backslash -> slash, drop '.' parts, fold 'x/..'."""
    out = []
    for c in p.replace("\\", "/").split("/"):
        if c in ("", "."):
            continue
        if c == ".." and out and out[-1] != "..":
            out.pop()
        else:
            out.append(c)
    return "/".join(out) or "."


def display(p):
    """Path as Ninja prints it: canonical, but keep original slashes if possible."""
    c = canon(p)
    return p if p.replace("\\", "/") == c else c


# ---------------------------------------------------------------- parser ---
class Parser:
    def __init__(self):
        self.root = Scope()
        self.root.rules["phony"] = {"name": "phony", "vars": {}}
        self.edges, self.defaults = [], []

    def parse_file(self, path, scope):
        with open(path, encoding="utf-8") as f:
            lx = Lexer(f.read(), path)
        while lx.p < len(lx.t):
            if lx.next_line_indented():
                lx.error("unexpected indent")
            if lx.p >= len(lx.t):
                break
            lx.skip_spaces()
            if lx.at_newline():                            # blank line
                lx.expect_newline()
                continue
            word = lx.ident()
            lx.skip_spaces()
            if word == "rule":
                self.parse_rule(lx, scope)
            elif word == "build":
                self.parse_build(lx, scope)
            elif word == "default":
                while not lx.at_newline():
                    self.defaults.append(canon(evaluate(lx.eval_string(True), scope.lookup)))
                lx.expect_newline()
            elif word in ("include", "subninja"):
                target = evaluate(lx.eval_string(False), scope.lookup).strip()
                lx.expect_newline()
                self.parse_file(target, scope if word == "include" else Scope(scope))
            elif word == "pool":
                lx.ident()
                lx.expect_newline()
                self.parse_bindings(lx)                    # depth = N; ignored here
            else:                                          # top-level variable
                if lx.peek() != "=":
                    lx.error(f"unknown statement {word!r}")
                lx.p += 1
                lx.skip_spaces()
                value = evaluate(lx.eval_string(False), scope.lookup)  # eager
                lx.expect_newline()
                scope.vars[word] = value

    def parse_bindings(self, lx):
        result = {}
        while lx.next_line_indented():
            lx.skip_spaces()
            key = lx.ident()
            lx.skip_spaces()
            if lx.peek() != "=":
                lx.error("expected '='")
            lx.p += 1
            lx.skip_spaces()
            result[key] = lx.eval_string(False)
            lx.expect_newline()
        return result

    def parse_rule(self, lx, scope):
        name = lx.ident()
        lx.expect_newline()
        if name in scope.rules:
            lx.error(f"duplicate rule {name!r}")
        rule = {"name": name, "vars": self.parse_bindings(lx)}
        if "command" not in rule["vars"]:
            lx.error(f"rule {name!r} has no command")
        scope.rules[name] = rule

    def parse_build(self, lx, scope):
        outs, imp_outs = [], []
        target = outs
        while True:                                        # outputs | implicit :
            c = lx.peek()
            if c == ":":
                lx.p += 1
                lx.skip_spaces()
                break
            if c == "|":
                lx.p += 1
                lx.skip_spaces()
                target = imp_outs
                continue
            if lx.at_newline():
                lx.error("expected ':'")
            target.append(lx.eval_string(True))
        rule_name = lx.ident()
        lx.skip_spaces()
        ins, imp_ins, order = [], [], []
        target = ins
        while not lx.at_newline():                         # inputs | implicit || order-only
            if lx.t.startswith("|@", lx.p):
                lx.error("validations (|@) not supported in this proof")
            if lx.t.startswith("||", lx.p):
                lx.p += 2
                lx.skip_spaces()
                target = order
                continue
            if lx.peek() == "|":
                lx.p += 1
                lx.skip_spaces()
                target = imp_ins
                continue
            target.append(lx.eval_string(True))
        lx.expect_newline()
        rule = scope.rule(rule_name)
        if rule is None:
            lx.error(f"unknown rule {rule_name!r}")
        edge = Edge(rule, scope)
        # build-level variables: evaluated now, against the file scope
        edge.bindings = {k: evaluate(v, scope.lookup) for k, v in self.parse_bindings(lx).items()}
        # paths: evaluated against build-level variables, then file scope
        look = lambda v: edge.bindings[v] if v in edge.bindings else scope.lookup(v)
        ev = lambda lst: [display(evaluate(x, look)) for x in lst if evaluate(x, look)]
        edge.outs, edge.implicit_outs = ev(outs), ev(imp_outs)
        edge.ins, edge.implicit_ins, edge.order_only = ev(ins), ev(imp_ins), ev(order)
        self.edges.append(edge)


# ------------------------------------------------------------ DAG build ---
def build_dag(parser, check_files=True):
    edges = parser.edges
    producer = {}                                          # canon(path) -> edge index
    for i, e in enumerate(edges):
        for o in e.all_outputs():
            k = canon(o)
            if k in producer:
                raise NinjaError(f"multiple rules generate {o}")
            producer[k] = i

    # dependency edges: j -> i  means edge i needs an output of edge j
    deps = [sorted({producer[canon(x)] for x in e.all_inputs() if canon(x) in producer})
            for e in edges]

    # targets: 'default' lines, else every output nobody consumes
    consumed = {canon(x) for e in edges for x in e.all_inputs()}
    targets = parser.defaults or [canon(o) for e in edges for o in e.all_outputs()
                                  if canon(o) not in consumed]

    # reachability from targets
    reach, stack = set(), [producer[t] for t in targets if t in producer]
    while stack:
        i = stack.pop()
        if i not in reach:
            reach.add(i)
            stack.extend(deps[i])

    # missing inputs: no producer and not on disk
    if check_files:
        for i in sorted(reach):
            for x in edges[i].all_inputs():
                if canon(x) not in producer and not os.path.exists(x):
                    raise NinjaError(f"'{x}', needed by '{edges[i].outs[0]}', "
                                     "missing and no known rule to make it")

    # Kahn: waiting count = number of distinct producers still unfinished
    waiting = {i: len(deps[i]) for i in reach}
    users = {i: [] for i in reach}
    for i in reach:
        for j in deps[i]:
            users[j].append(i)
    ready = deque(sorted(i for i in reach if waiting[i] == 0))
    order = []
    while ready:
        i = ready.popleft()
        order.append(i)
        for u in users[i]:
            waiting[u] -= 1
            if waiting[u] == 0:
                ready.append(u)
    if len(order) != len(reach):
        stuck = sorted(set(reach) - set(order))
        raise NinjaError("dependency cycle among: " + ", ".join(edges[i].outs[0] for i in stuck))
    return {"producer": producer, "deps": deps, "targets": targets,
            "reach": reach, "order": order}


def load(build_ninja):
    """Parse build.ninja (paths are relative to its folder, like Ninja)."""
    d, f = os.path.split(os.path.abspath(build_ninja))
    old = os.getcwd()
    os.chdir(d)
    try:
        p = Parser()
        p.parse_file(f, p.root)
        return p, build_dag(p)
    finally:
        os.chdir(old)


if __name__ == "__main__":
    p, g = load(sys.argv[1])
    print(f"parsed {len(p.edges)} build statements, {len(p.root.rules)} rules, "
          f"default targets = {p.defaults}")
    print(f"reachable from defaults: {len(g['reach'])} edges; topological order:")
    for n, i in enumerate(g["order"], 1):
        e = p.edges[i]
        need = [p.edges[j].outs[0] for j in g["deps"][i]]
        print(f"  {n}. [{e.rule['name']}] {e.outs[0]}   waits for: {need or '-'}")
