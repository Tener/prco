"""Rendering helpers for PR review reports.

Saves the LLM from re-deriving syntax coloring + the report HTML each
review. Stdlib only -- imported from a generator script in the
worktree and run with plain python3:

    python3 generate_report.<suffix>.py

Typical usage:

    from PR_RENDER import (render_report, render_snippet, render_trace,
                           render_sequence, from_file)

    snippet = from_file(
        "lib/srv/db/common/auth.go",
        1119, 1148,
        hl_lines=[1125, 1126],
    )

    html_doc = render_report(
        meta={
            "reviewer":    "Claude Opus 4.7",
            "generated":   "2026-05-20T14:32:11+02:00",
            "pr":          61168,
            "url":         "https://github.com/gravitational/teleport/pull/61168",
            "head_commit": "abc123...",  # full SHA
            "base_branch": "master",
        },
        findings=[
            {
                "id":          "1-null-deref",
                "severity":    "high",          # blocker|high|medium|low|nit
                "location":    "lib/srv/db/common/auth.go:1119-1148",
                "category":    "a",             # a|b|c|d from step 7
                "rule":        "R2",            # or None
                "bluf":        "Helper drops the invariant",  # few-word bottom line
                # Required. What the affected person sees and can(not) do,
                # in their terms; never a restatement of the code.
                "impact":      "<p>Users with long-lived sessions send ...</p>",
                "description": "<p>The helper ...</p>",
                # Required for blocker/high/medium, optional below. The
                # unstated assumptions the failure chain depends on, each
                # rated on the fixed likelihood scale, plus a combined
                # verdict (weakest necessary link).
                "assumptions": {
                    "rows": [
                        ("An admin repoints the app at another upstream",
                         "low", "Privileged, audited action; migrations make it plausible"),
                        ("A session is live within the window",
                         "high", "Clients run for hours and reconnect on error"),
                    ],
                    "overall": ("low", "Needs a privileged actor; then near-certain"),
                },
                # Minimal repro. A failing test or code excerpt goes
                # through render_snippet; a step-by-step scenario goes
                # through render_trace (numbered prose steps, `code`
                # spans, optional expected/actual footer); timing or
                # ordering across several parties (a race, cache skew,
                # a replay) goes through render_sequence (inline-SVG
                # sequence diagram). Never put prose steps in a code
                # block behind // comments.
                "repro":       render_trace(
                    ["run `tsh mcp login sentry`",
                     ("token expires", "provider issued no refresh token"),
                     ("client request", ["GetAuthHeader -> refresh", "probe returns 200"])],
                    preamble="Source trace; not a cluster run.",
                    expected="request is sent without a header",
                    actual="login-required error on every request",
                ),
                "action":      "<p>State the invariant ...</p>",
                "snippets":    [snippet],
            },
        ],
    )
    open("PR_REVIEW_REPORT.<suffix>.html", "w").write(html_doc)

Findings are grouped by severity (Blocker > High > Medium > Low >
Nit) in the document; input order is preserved inside each group.

Likelihood scale (LIKELIHOODS): very-low, low, low-to-medium, medium,
high. Any other value raises. Likelihood and severity are separate
judgments: a high-severity, low-likelihood finding is a legitimate
outcome and the table is where that split is made visible.
"""
import html
import json
import re

CSS_CLASS = "hl"


# ---------------------------------------------------------------------------
# Snippet rendering: stdlib syntax coloring.
# ---------------------------------------------------------------------------
# Token classes: kw (keyword), str (string), com (comment), num (number).
# One regex alternation per language, applied to the whole snippet (not
# per line) so block comments and raw/triple-quoted strings can span
# lines. Spans are split at newlines, so each rendered line is
# self-contained inside the gutter table.

_NUMBER = r"\b(?:0[xXbBoO][0-9a-fA-F_]+|\d[\d_]*(?:\.\d+)?(?:[eE][+-]?\d+)?)\b"
_WORD = r"[A-Za-z_][A-Za-z0-9_]*"
_DQ = r'"(?:\\.|[^"\\\n])*"'   # double-quoted, backslash escapes, one line
_SQ = r"'(?:\\.|[^'\\\n])*'"   # single-quoted, backslash escapes, one line

_LANG_SPECS = {
    "go": dict(
        line_comment=r"//",
        block_comment=(r"/\*", r"\*/"),
        strings=(r"`[^`]*`", _DQ, _SQ),
        keywords=frozenset("""
            break case chan const continue default defer else fallthrough
            for func go goto if import interface map package range return
            select struct switch type var nil true false iota
        """.split()),
    ),
    "python": dict(
        line_comment=r"#",
        strings=(
            r"(?:[rRbBuUfF]{1,2})?'''.*?(?:'''|\Z)",
            r'(?:[rRbBuUfF]{1,2})?""".*?(?:"""|\Z)',
            r"(?:[rRbBuUfF]{1,2})?" + _DQ,
            r"(?:[rRbBuUfF]{1,2})?" + _SQ,
        ),
        keywords=frozenset("""
            False None True and as assert async await break class continue
            def del elif else except finally for from global if import in is
            lambda match nonlocal not or pass raise return self try while
            with yield case
        """.split()),
    ),
    "typescript": dict(
        line_comment=r"//",
        block_comment=(r"/\*", r"\*/"),
        strings=(r"`(?:\\.|[^`\\])*`", _DQ, _SQ),
        keywords=frozenset("""
            abstract any as async await boolean break case catch class const
            continue debugger declare default delete do else enum export
            extends false finally for from function get if implements import
            in instanceof interface is keyof let namespace never new null
            number of private protected public readonly return set static
            string super switch this throw true try type typeof undefined
            unknown var void while with yield
        """.split()),
    ),
    "bash": dict(
        line_comment=r"#",
        strings=(_DQ, _SQ),
        keywords=frozenset("""
            if then else elif fi for while until do done case esac function
            in select time return break continue local export readonly
            declare unset shift exit trap set eval exec source true false
        """.split()),
    ),
    "rust": dict(
        line_comment=r"//",
        block_comment=(r"/\*", r"\*/"),
        strings=(_DQ,),  # no single quotes: 'a is a lifetime, not a string
        keywords=frozenset("""
            as async await box break const continue crate dyn else enum
            extern false fn for if impl in let loop match mod move mut pub
            ref return self Self static struct super trait true type unsafe
            use where while
        """.split()),
    ),
    "proto": dict(
        line_comment=r"//",
        block_comment=(r"/\*", r"\*/"),
        strings=(_DQ,),
        keywords=frozenset("""
            syntax package import option message enum service rpc returns
            stream repeated optional required oneof map reserved extend
            extensions true false string bytes bool double float int32 int64
            uint32 uint64 sint32 sint64 fixed32 fixed64 sfixed32 sfixed64
        """.split()),
    ),
    "yaml": dict(
        line_comment=r"#",
        strings=(_DQ, _SQ),
        keywords=frozenset("true false null yes no on off".split()),
    ),
    "toml": dict(
        line_comment=r"#",
        strings=(r'""".*?(?:"""|\Z)', _DQ, _SQ),
        keywords=frozenset("true false".split()),
    ),
    "json": dict(
        strings=(_DQ,),
        keywords=frozenset("true false null".split()),
    ),
    "sql": dict(
        line_comment=r"--",
        block_comment=(r"/\*", r"\*/"),
        strings=(_SQ,),
        ci_keywords=True,
        keywords=frozenset("""
            SELECT FROM WHERE AND OR NOT NULL IN IS LIKE BETWEEN EXISTS
            INSERT INTO VALUES UPDATE SET DELETE CREATE TABLE INDEX VIEW
            DROP ALTER ADD COLUMN PRIMARY KEY FOREIGN REFERENCES UNIQUE
            DEFAULT JOIN LEFT RIGHT INNER OUTER FULL CROSS ON AS GROUP BY
            ORDER HAVING LIMIT OFFSET UNION ALL DISTINCT CASE WHEN THEN
            ELSE END BEGIN COMMIT ROLLBACK TRANSACTION
        """.split()),
    ),
}
_LANG_SPECS["javascript"] = _LANG_SPECS["typescript"]


def _compile(spec):
    """Build (regex, group index -> token class) for one language spec.

    Alternation order matters: comments, then strings, then numbers,
    then words. The regex engine tries alternatives at each text
    position, so a '#' inside a string never starts a comment (the
    string alternative consumes past it first).
    """
    parts, classes = [], []

    def add(cls, pattern):
        parts.append(f"(?P<g{len(classes)}>{pattern})")
        classes.append(cls)

    if "block_comment" in spec:
        opener, closer = spec["block_comment"]
        add("com", f"{opener}.*?(?:{closer}|\\Z)")
    if "line_comment" in spec:
        add("com", spec["line_comment"] + r"[^\n]*")
    for s in spec.get("strings", ()):
        add("str", s)
    add("num", _NUMBER)
    add("word", _WORD)
    return re.compile("|".join(parts), re.S), classes


_COMPILED = {
    name: (*_compile(spec), spec) for name, spec in _LANG_SPECS.items()
}


def _tokens(code, lexer):
    """Yield (token_class_or_None, text) pairs covering all of `code`."""
    compiled = _COMPILED.get(lexer)
    if compiled is None:
        yield None, code
        return
    rx, classes, spec = compiled
    pos = 0
    for m in rx.finditer(code):
        if m.start() > pos:
            yield None, code[pos:m.start()]
        cls, text = classes[int(m.lastgroup[1:])], m.group()
        if cls == "word":
            word = text.upper() if spec.get("ci_keywords") else text
            cls = "kw" if word in spec["keywords"] else None
        yield cls, text
        pos = m.end()
    if pos < len(code):
        yield None, code[pos:]


def _highlight_lines(code, lexer):
    """HTML for each line of `code`: tokens in spans, all text escaped.
    Spans never cross newlines."""
    lines = [[]]
    for cls, text in _tokens(code, lexer):
        for i, part in enumerate(text.split("\n")):
            if i:
                lines.append([])
            if not part:
                continue
            esc = html.escape(part)
            lines[-1].append(f'<span class="{cls}">{esc}</span>' if cls else esc)
    return ["".join(parts) for parts in lines]


def style_css() -> str:
    """Token palette + line-highlight CSS for a single inline <style>
    block. render_report() emits this automatically; call it directly
    only if you embed snippets outside the standard report."""
    c = CSS_CLASS
    return (
        f".{c} .kw  {{ color: #c678dd; font-weight: 600; }}\n"
        f".{c} .str {{ color: #98c379; }}\n"
        f".{c} .com {{ color: #7f848e; font-style: italic; }}\n"
        f".{c} .num {{ color: #d19a66; }}\n"
        f".{c} .hll {{ display: block; background: rgba(255, 213, 79, 0.12); }}\n"
        f".{c} td.code {{ width: 100%; }}\n"
    )


def render_snippet(code: str, *, lexer: str = "go",
                   first_line: int = 1, hl_lines=None) -> str:
    """One syntax-colored code block.

    code:       snippet text.
    lexer:      language name (`go`, `python`, `proto`, ...); unknown
                names render as escaped plain text.
    first_line: 1-based file line of code's first line; shown in the
                gutter and used to translate hl_lines.
    hl_lines:   absolute file line numbers to emphasize.
    """
    hl = set(hl_lines or [])
    lines = _highlight_lines(code.rstrip("\n"), lexer)
    gutter = "\n".join(str(first_line + i) for i in range(len(lines)))
    body = "".join(
        f'<span class="hll">{line}\n</span>' if first_line + i in hl
        else f"{line}\n"
        for i, line in enumerate(lines)
    )
    return (
        f'<div class="{CSS_CLASS}"><table><tr>'
        f'<td class="linenos"><pre>{gutter}</pre></td>'
        f'<td class="code"><pre>{body}</pre></td>'
        f'</tr></table></div>'
    )


def from_file(path: str, start_line: int, end_line: int, *,
              lexer: str | None = None, hl_lines=None) -> str:
    """Render lines [start_line, end_line] of `path` (1-based, inclusive).

    `lexer` defaults to a guess from the extension; pass explicitly to
    override or for files whose extension isn't covered below. Unknown
    languages render as escaped plain text.
    """
    with open(path) as f:
        lines = f.readlines()
    snippet = "".join(lines[start_line - 1:end_line])
    if lexer is None:
        lexer = _guess_lexer(path)
    return render_snippet(snippet, lexer=lexer,
                          first_line=start_line, hl_lines=hl_lines)


def _inline(text: str) -> str:
    """Escape prose, turn `backticks` into <code>, and ' -> ' into an arrow."""
    out = []
    for part in re.split(r"(`[^`\n]*`)", str(text)):
        if len(part) >= 2 and part.startswith("`") and part.endswith("`"):
            out.append(f"<code>{html.escape(part[1:-1])}</code>")
        else:
            out.append(html.escape(part).replace(" -&gt; ", " → "))
    return "".join(out)


def _trace_items(steps) -> str:
    items = []
    for step in steps:
        note = ""
        children = ""
        if isinstance(step, (tuple, list)):
            if len(step) != 2:
                raise ValueError(f"trace step must be text, (text, note) or (text, [substeps]); got {step!r}")
            text, extra = step
            if isinstance(extra, (list, tuple)):
                children = f"<ol>{_trace_items(extra)}</ol>"
            elif extra:
                note = f'<span class="note">{_inline(extra)}</span>'
        else:
            text = step
        items.append(f"<li>{_inline(text)}{note}{children}</li>")
    return "".join(items)


def render_trace(steps, *, preamble=None, expected=None, actual=None) -> str:
    """A scenario repro: numbered steps in prose, not a code block.

    steps:    list of steps. Each is a string, a (text, note) pair where
              note is a dimmed observation shown after the step, or a
              (text, [substeps]) pair for a nested list. In any text,
              `backticks` render as code and ' -> ' as an arrow.
    preamble: optional dimmed line above the steps, e.g. "Source trace;
              not a cluster run."
    expected: optional "what should happen" line.
    actual:   optional "what happens" line.

    Use this for step-by-step scenarios (user actions, timing, call
    chains). Use render_snippet for a failing test, a code excerpt, or a
    shell transcript.
    """
    if not steps:
        raise ValueError("render_trace needs at least one step")
    pre = f'<p class="trace-pre">{_inline(preamble)}</p>' if preamble else ""
    outcome = ""
    if expected or actual:
        rows = []
        if expected:
            rows.append(f'<span class="lbl exp">Expected</span><span>{_inline(expected)}</span>')
        if actual:
            rows.append(f'<span class="lbl act">Actual</span><span>{_inline(actual)}</span>')
        outcome = f'<div class="trace-outcome">{"".join(rows)}</div>'
    return f'<div class="trace">{pre}<ol>{_trace_items(steps)}</ol>{outcome}</div>'


# ---------------------------------------------------------------------------
# Sequence diagrams: inline SVG, no external resources.
# ---------------------------------------------------------------------------

_SEQ_FONT = 13
_SEQ_PAD = 12
_SEQ_HEAD_H = 30
_SEQ_ROW = 38
_SEQ_KINDS = {
    #          stroke     dash   marker
    "call":   ("#9fb4c8", "",    "n"),
    "reply":  ("#9fb4c8", "6 4", "n"),
    "danger": ("#e74c3c", "",    "d"),
    "fail":   ("#e74c3c", "6 4", "d"),
}
_seq_counter = [0]


def _seq_px(text: str) -> float:
    """Approximate rendered width of text at _SEQ_FONT."""
    return len(re.sub(r"`", "", str(text))) * _SEQ_FONT * 0.6


def _seq_text(x, y, text, *, anchor="middle", fill="#d6dbe1", size=_SEQ_FONT, italic=False):
    """SVG <text> with `backticks` as monospace tspans."""
    spans = []
    for part in re.split(r"(`[^`\n]*`)", str(text)):
        if not part:
            continue
        if len(part) >= 2 and part.startswith("`") and part.endswith("`"):
            spans.append(f'<tspan font-family="ui-monospace, Menlo, monospace" '
                         f'font-size="{size - 1}" fill="#e6e9ee">{html.escape(part[1:-1])}</tspan>')
        else:
            spans.append(html.escape(part))
    style = ' font-style="italic"' if italic else ""
    # A background-colored stroke painted under the glyphs keeps lifelines
    # and arrows from cutting through labels that cross them.
    halo = ' stroke="#14171a" stroke-width="4" paint-order="stroke" stroke-linejoin="round"'
    return (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" fill="{fill}" '
            f'font-size="{size}"{style}{halo}>{"".join(spans)}</text>')


def render_sequence(participants, events, *, caption=None) -> str:
    """A sequence diagram as inline SVG (stdlib only, self-contained).

    participants: list of names in left-to-right order.
    events:       list of tuples, in time order:
        ("msg",  src, dst, label[, kind])  arrow from src to dst. kind is
                 "call" (solid, default), "reply" (dashed), "danger"
                 (solid red: the harmful message), or "fail" (dashed red).
                 src == dst draws a self-message.
        ("note", participant_or_list, text)  a note box over one or more
                 participants.
        ("mark", text)  a full-width divider with a label, e.g. "t = 60 s".
    caption:      optional dimmed line under the diagram.

    Labels render `backticks` in monospace. Use this for timing and
    ordering across several parties (races, cache skew, replay); use
    render_trace for a single actor's steps.
    """
    if not participants:
        raise ValueError("render_sequence needs at least one participant")
    if not events:
        raise ValueError("render_sequence needs at least one event")
    names = list(participants)
    index = {n: i for i, n in enumerate(names)}
    _seq_counter[0] += 1
    uid = f"seq{_seq_counter[0]}"

    def require_index(name):
        if name not in index:
            raise ValueError(f"unknown participant {name!r}; known: {names}")
        return index[name]

    # Header boxes hug their labels; column spacing is the widest thing
    # that has to fit between two adjacent lifelines: half a header box on
    # each side, or a message label divided by the columns it spans.
    head_w = [min(max(_seq_px(n) + 20, 80), 260) for n in names]
    need = [90.0]
    for i in range(len(names) - 1):
        need.append(head_w[i] / 2 + head_w[i + 1] / 2 + 16)
    overhang_right = 0.0
    for e in events:
        if e[0] != "msg" or len(e) < 4:
            continue
        i, j = require_index(e[1]), require_index(e[2])
        if i == j:
            # Self message: label sits to the right of the lifeline.
            span = 34 + 8 + _seq_px(e[3])
            if j == len(names) - 1:
                overhang_right = max(overhang_right, span)
            elif len(names) > 1:
                need.append(span + 12)
        else:
            need.append((_seq_px(e[3]) + 24) / abs(i - j))
    col_w = min(max(need), 260)
    xs = [_SEQ_PAD + head_w[0] / 2 + i * col_w for i in range(len(names))]
    width = xs[-1] + max(head_w[-1] / 2, overhang_right) + _SEQ_PAD
    # Notes centred on an edge participant may poke out; widen for them.
    for e in events:
        if e[0] == "note" and len(e) == 3:
            over = [e[1]] if isinstance(e[1], str) else list(e[1])
            cx = sum(xs[require_index(p)] for p in over) / len(over)
            half = (max(_seq_px(l) for l in str(e[2]).split("\n")) + 18) / 2
            width = max(width, cx + half + _SEQ_PAD)
            if cx - half < _SEQ_PAD:
                shift = _SEQ_PAD - (cx - half)
                xs = [x + shift for x in xs]
                width += shift

    body = []
    y = _SEQ_PAD + _SEQ_HEAD_H + 22

    def require(name):
        return xs[require_index(name)]

    for ev in events:
        kind = ev[0]
        if kind == "msg":
            if len(ev) not in (4, 5):
                raise ValueError(f"msg event must be (\"msg\", src, dst, label[, kind]); got {ev!r}")
            _, src, dst, label = ev[:4]
            style = ev[4] if len(ev) == 5 else "call"
            if style not in _SEQ_KINDS:
                raise ValueError(f"unknown message kind {style!r}; expected one of {sorted(_SEQ_KINDS)}")
            stroke, dash, marker = _SEQ_KINDS[style]
            dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
            x1, x2 = require(src), require(dst)
            if src == dst:
                lx = x1 + 34
                body.append(
                    f'<path d="M{x1:.1f},{y + 4:.1f} H{lx:.1f} V{y + 20:.1f} H{x1 + 6:.1f}" fill="none" '
                    f'stroke="{stroke}" stroke-width="1.5"{dash_attr} marker-end="url(#{uid}-{marker})"/>')
                body.append(_seq_text(lx + 8, y + 16, label, anchor="start"))
                y += _SEQ_ROW + 6
            else:
                body.append(_seq_text((x1 + x2) / 2, y + 4, label))
                body.append(
                    f'<line x1="{x1:.1f}" y1="{y + 12:.1f}" x2="{x2:.1f}" y2="{y + 12:.1f}" '
                    f'stroke="{stroke}" stroke-width="1.5"{dash_attr} marker-end="url(#{uid}-{marker})"/>')
                y += _SEQ_ROW
        elif kind == "note":
            if len(ev) != 3:
                raise ValueError(f"note event must be (\"note\", participants, text); got {ev!r}")
            _, over, text = ev
            over = [over] if isinstance(over, str) else list(over)
            cx = sum(require(p) for p in over) / len(over)
            lines = str(text).split("\n")
            w = max(_seq_px(l) for l in lines) + 18
            h = 10 + 16 * len(lines)
            body.append(
                f'<rect x="{cx - w / 2:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h}" rx="3" '
                f'fill="#2a2d23" stroke="#6b6b3a"/>')
            for i, line in enumerate(lines):
                body.append(_seq_text(cx, y + 17 + 16 * i, line, fill="#e6e3c4", size=_SEQ_FONT - 1))
            y += h + 12
        elif kind == "mark":
            if len(ev) != 2:
                raise ValueError(f"mark event must be (\"mark\", text); got {ev!r}")
            body.append(
                f'<line x1="{_SEQ_PAD}" y1="{y + 12:.1f}" x2="{width - _SEQ_PAD}" y2="{y + 12:.1f}" '
                f'stroke="#3a424b" stroke-dasharray="3 5"/>')
            body.append(_seq_text(_SEQ_PAD, y + 8, ev[1], anchor="start", fill="#98a2ad",
                                  size=_SEQ_FONT - 1, italic=True))
            y += 30
        else:
            raise ValueError(f"unknown event kind {kind!r}; expected msg, note or mark")

    y_end = y + 6
    height = y_end + _SEQ_PAD
    head = []
    for name, x, bw in zip(names, xs, head_w):
        head.append(
            f'<rect x="{x - bw / 2:.1f}" y="{_SEQ_PAD}" width="{bw:.1f}" height="{_SEQ_HEAD_H}" rx="3" '
            f'fill="#20252b" stroke="#3a424b"/>')
        head.append(_seq_text(x, _SEQ_PAD + _SEQ_HEAD_H / 2 + 4, name, fill="#eef1f5"))
        head.append(
            f'<line x1="{x:.1f}" y1="{_SEQ_PAD + _SEQ_HEAD_H}" x2="{x:.1f}" y2="{y_end:.1f}" '
            f'stroke="#3a424b" stroke-dasharray="4 4"/>')

    defs = (
        f'<defs>'
        f'<marker id="{uid}-n" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">'
        f'<path d="M0,0 L8,4 L0,8 z" fill="#9fb4c8"/></marker>'
        f'<marker id="{uid}-d" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">'
        f'<path d="M0,0 L8,4 L0,8 z" fill="#e74c3c"/></marker>'
        f'</defs>'
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'width="{width:.0f}" height="{height:.0f}" role="img" '
        f'font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif">'
        f'{defs}<rect width="100%" height="100%" fill="#14171a"/>'
        f'{"".join(head)}{"".join(body)}</svg>'
    )
    cap = f'<p class="seq-caption">{_inline(caption)}</p>' if caption else ""
    return f'<div class="seq">{svg}{cap}</div>'


def _guess_lexer(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower()
    return {
        "go":    "go",
        "py":    "python",
        "ts":    "typescript",
        "tsx":   "typescript",
        "js":    "javascript",
        "jsx":   "javascript",
        "sh":    "bash",
        "bash":  "bash",
        "rs":    "rust",
        "proto": "proto",
        "yaml":  "yaml",
        "yml":   "yaml",
        "json":  "json",
        "md":    "markdown",
        "toml":  "toml",
        "sql":   "sql",
    }.get(ext, "text")


# ---------------------------------------------------------------------------
# Full report rendering.
# ---------------------------------------------------------------------------

_SEVERITY_ORDER = ("blocker", "high", "medium", "low", "nit")
_SEVERITY_LABEL = {
    "blocker": "Blocker",
    "high":    "High",
    "medium":  "Medium",
    "low":     "Low",
    "nit":     "Nit",
}

# Severities for which the threat-model assumptions table is mandatory.
_ASSUMPTIONS_REQUIRED_FOR = ("blocker", "high", "medium")

# Fixed likelihood vocabulary for the assumptions table. Kept small so
# ratings are comparable across findings and across reports.
LIKELIHOODS = ("very-low", "low", "low-to-medium", "medium", "high")
_LIKELIHOOD_LABEL = {
    "very-low":      "Very low",
    "low":           "Low",
    "low-to-medium": "Low to medium",
    "medium":        "Medium",
    "high":          "High",
}

_REPORT_CSS = """
:root { color-scheme: dark; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    line-height: 1.5;
    /* Two-tier layout: the container is wide enough for tables, code and
       diagrams (80rem, GitHub's content width); prose blocks are capped
       separately at ~70 characters, the readable measure. */
    max-width: 80rem;
    margin: 1.25rem auto;
    padding: 0 1.5rem;
    color: #d6dbe1;
    background: #16191d;
}
h1 { font-size: 1.6rem; margin: 0 0 0.5rem; }
h2 {
    font-size: 1.3rem;
    margin: 2.5rem 0 1rem;
    border-bottom: 2px solid #2e343b;
    padding-bottom: 0.25rem;
}
code, .mono {
    font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
}

.meta {
    background: #1d2126;
    border: 1px solid #2e343b;
    border-radius: 4px;
    padding: 0.75rem 1rem;
    margin-bottom: 1.5rem;
    font-size: 0.9rem;
}
.meta dl {
    margin: 0;
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: 0.25rem 0.75rem;
}
.meta dt { font-weight: 600; color: #98a2ad; margin: 0; }
.meta dd { margin: 0; }
a { color: #6cb6ff; }

.finding {
    border: 1px solid #2e343b;
    border-left: 4px solid #6b7480;
    border-radius: 4px;
    padding: 1rem 1.25rem;
    margin-bottom: 1.25rem;
    background: #1d2126;
}
.finding.blocker { border-left-color: #e74c3c; }
.finding.high    { border-left-color: #e67e22; }
.finding.medium  { border-left-color: #f1c40f; }
.finding.low     { border-left-color: #3498db; }
.finding.nit     { border-left-color: #95a5a6; }

.finding-head {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 0.4rem 0.75rem;
    margin-bottom: 0.75rem;
}
.finding-id { font-weight: 600; }
.bluf {
    font-weight: 600;
    font-size: 1.02rem;
    color: #eef1f5;
    margin: 0.1rem 0 0.6rem;
}
.badge {
    display: inline-block;
    padding: 0.1rem 0.5rem;
    border-radius: 3px;
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.02em;
    background: #2e343b;
    color: #d6dbe1;
}
.badge.blocker { background: #e74c3c; color: #fff; }
.badge.high    { background: #e67e22; color: #1a1a1a; }
.badge.medium  { background: #f1c40f; color: #1a1a1a; }
.badge.low     { background: #3498db; color: #fff; }
.badge.nit     { background: #95a5a6; color: #1a1a1a; }
.badge.rule    { background: #a371d6; color: #1a1a1a; }
.badge.cat     { background: #4a5a6b; color: #fff; }
.location {
    font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
    color: #9fb4c8;
}

.copy {
    background: none;
    border: 1px solid #3a414a;
    border-radius: 3px;
    padding: 0 0.4rem;
    font-size: 0.7rem;
    color: #98a2ad;
    cursor: pointer;
    font-family: inherit;
}
.copy:hover { background: #262c33; }
.copy:active { background: #2e353d; }

.section { margin-top: 0.75rem; }
/* Two tiers only. Every text block (bluf, impact, prose, assumptions
   table) shares one right edge and one font size so the eye scans a
   single column; code snippets and diagrams span the whole card. */
:root { --text-width: 120ch; --text-size: 0.95rem; }
.prose, .impact, .bluf, .assumptions table {
    max-width: var(--text-width);
    font-size: var(--text-size);
}
.bluf { font-size: 1.02rem; }
.section-label {
    font-weight: 600;
    color: #98a2ad;
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    margin-bottom: 0.25rem;
}

/* User impact: a callout that reads apart from the severity palette. */
.impact {
    margin: 0 0 0.9rem;
    padding: 0.6rem 0.9rem;
    border-left: 4px solid #1abc9c;
    border-radius: 0 4px 4px 0;
    background: rgba(26, 188, 156, 0.10);
    color: #e6f7f3;
}
.impact > .impact-label {
    display: block;
    margin-bottom: 0.25rem;
    color: #1abc9c;
    font-weight: 600;
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}
.impact p { margin: 0.2rem 0; }
.impact code { color: #d6dbe1; }

/* Scenario repro: numbered prose steps. */
.trace {
    border: 1px solid #2e343b;
    border-radius: 3px;
    background: #14171a;
    padding: 0.6rem 0.9rem;
    font-size: 0.92rem;
}
.trace ol { margin: 0.1rem 0 0.1rem 1.5rem; padding: 0; }
.trace ol ol { margin-top: 0.2rem; list-style: lower-alpha; }
.trace li { margin: 0.25rem 0; }
.trace li::marker { color: #98a2ad; font-weight: 600; }
.trace code {
    background: #1f242a;
    border: 1px solid #2e343b;
    border-radius: 3px;
    padding: 0 0.3rem;
    font-size: 0.88em;
    color: #e6e9ee;
}
.trace .note { color: #98a2ad; font-style: italic; margin-left: 0.5rem; }
.trace-pre { margin: 0 0 0.4rem; color: #98a2ad; font-style: italic; }
.trace-outcome {
    margin-top: 0.6rem;
    padding-top: 0.5rem;
    border-top: 1px solid #2e343b;
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: 0.3rem 0.7rem;
    align-items: baseline;
}
.lbl {
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    padding: 0.05rem 0.45rem;
    border-radius: 3px;
}
.lbl.exp { background: #2e7d32; color: #fff; }
.lbl.act { background: #c0392b; color: #fff; }

/* Sequence diagram (inline SVG). */
.seq {
    border: 1px solid #2e343b;
    border-radius: 3px;
    background: #14171a;
    overflow-x: auto;
    padding: 0.25rem;
}
/* Intrinsic size: a wide diagram scrolls inside its box rather than
   shrinking its text below readability. */
.seq svg { display: block; }
.seq-caption { margin: 0.3rem 0.5rem 0.2rem; color: #98a2ad; font-style: italic; font-size: 0.85rem; }

/* Threat-model assumptions table. */
.assumptions { margin-top: 0.9rem; }
.assumptions table {
    width: 100%;
    border-collapse: collapse;
    background: #1a1e23;
    border: 1px solid #2e343b;
}
.assumptions th, .assumptions td {
    padding: 0.45rem 0.65rem;
    border-bottom: 1px solid #2e343b;
    vertical-align: top;
    text-align: left;
}
.assumptions th { color: #98a2ad; font-weight: 600; background: #20252b; }
.assumptions td:nth-child(2) { white-space: nowrap; }
.assumptions tr.overall td { background: #20252b; border-top: 2px solid #3a424b; }
.lk {
    display: inline-block;
    padding: 0.05rem 0.5rem;
    border-radius: 10px;
    font-size: 0.78rem;
    font-weight: 600;
    color: #fff;
}
.lk.very-low       { background: #4b5563; }
.lk.low            { background: #2e86c1; }
.lk.low-to-medium  { background: #7d8f3c; }
.lk.medium         { background: #c9a227; color: #1a1e23; }
.lk.high           { background: #d35400; }

.hl { font-size: 0.85rem; overflow-x: auto; border: 1px solid #2e343b; border-radius: 3px; background: #14171a; }
.hl table { border-spacing: 0; width: 100%; }
.hl td { padding: 0; vertical-align: top; }
.hl .linenos {
    color: #6b7480;
    text-align: right;
    user-select: none;
    padding: 0.5em 0.6em;
    border-right: 1px solid #2e343b;
    background: #181c20;
}
.hl pre { margin: 0; padding: 0.5em 0.75em; }
"""

_REPORT_JS = """
function copy(value, btn) {
    navigator.clipboard.writeText(value).then(function () {
        var orig = btn.textContent;
        btn.textContent = 'Copied';
        setTimeout(function () { btn.textContent = orig; }, 1000);
    });
}
"""


def _copy_btn(value: str) -> str:
    """A small Copy button that writes `value` to the clipboard."""
    js_arg = json.dumps(value)  # JSON-encode for safe embedding as JS literal
    attr = html.escape(f"copy({js_arg}, this)", quote=True)
    return f'<button class="copy" type="button" onclick="{attr}">Copy</button>'


def _render_meta(meta: dict) -> str:
    pr = meta["pr"]
    url = meta["url"]
    head = meta["head_commit"]
    rows = [
        ("Reviewer",    html.escape(str(meta["reviewer"]))),
        ("Generated",   html.escape(str(meta["generated"]))),
        ("PR",          f'<a href="{html.escape(url, quote=True)}">#{pr}</a> '
                        f'{_copy_btn(url)}'),
        ("Head commit", f'<span class="mono">{html.escape(head)}</span> '
                        f'{_copy_btn(head)}'),
        ("Base branch", html.escape(str(meta["base_branch"]))),
    ]
    items = "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in rows)
    return f'<div class="meta"><dl>{items}</dl></div>'


def _likelihood_badge(value, fid) -> str:
    key = str(value).lower()
    if key not in _LIKELIHOOD_LABEL:
        raise ValueError(
            f"unknown likelihood {value!r} in finding {fid!r}; "
            f"expected one of {', '.join(LIKELIHOODS)}")
    return f'<span class="lk {key}">{_LIKELIHOOD_LABEL[key]}</span>'


def _render_assumptions(a, fid) -> str:
    """The threat-model assumptions table.

    a: {"rows": [(assumption_html, likelihood, rationale_html), ...],
        "overall": (likelihood, rationale_html)}
    """
    rows = a.get("rows") or []
    if not rows:
        raise ValueError(f"assumptions.rows is empty in finding {fid!r}")
    body = []
    for row in rows:
        if len(row) != 3:
            raise ValueError(
                f"assumptions row must be (assumption, likelihood, rationale) "
                f"in finding {fid!r}: {row!r}")
        assumption, lk, rationale = row
        body.append(f"<tr><td>{assumption}</td><td>{_likelihood_badge(lk, fid)}</td>"
                    f"<td>{rationale}</td></tr>")
    overall = a.get("overall")
    if not overall or len(overall) != 2:
        raise ValueError(
            f"assumptions.overall must be (likelihood, rationale) in finding {fid!r}")
    lk, rationale = overall
    body.append(f'<tr class="overall"><td><b>Combined likelihood</b></td>'
                f'<td>{_likelihood_badge(lk, fid)}</td><td>{rationale}</td></tr>')
    return (
        '<div class="assumptions"><div class="section-label">Threat-model assumptions</div>'
        '<table><thead><tr><th>Unstated assumption</th><th>Likelihood</th><th>Why</th>'
        f'</tr></thead><tbody>{"".join(body)}</tbody></table></div>'
    )


def _render_finding(f: dict) -> str:
    fid = f.get("id")
    sev = f["severity"].lower()
    if sev not in _SEVERITY_LABEL:
        raise ValueError(f"unknown severity {sev!r} in finding {fid!r}")

    impact = f.get("impact")
    if not impact or not str(impact).strip():
        raise ValueError(
            f"finding {fid!r} has no impact; every finding must say what the "
            f"affected person sees and can(not) do")

    assumptions = f.get("assumptions")
    if assumptions is None and sev in _ASSUMPTIONS_REQUIRED_FOR:
        raise ValueError(
            f"finding {fid!r} ({sev}) has no assumptions table; it is mandatory "
            f"for severities {', '.join(_ASSUMPTIONS_REQUIRED_FOR)}")

    badges = [f'<span class="badge {sev}">{_SEVERITY_LABEL[sev]}</span>',
              f'<span class="badge cat">{html.escape(f["category"].upper())}</span>']
    if f.get("rule"):
        badges.append(f'<span class="badge rule">{html.escape(f["rule"])}</span>')

    snippets_html = "".join(
        f'<div class="section">{s}</div>' for s in f.get("snippets", [])
    )

    bluf_html = f'<div class="bluf">{f["bluf"]}</div>' if f.get("bluf") else ""

    impact_html = (f'<div class="impact"><span class="impact-label">User impact</span>'
                   f'{impact}</div>')

    assumptions_html = _render_assumptions(assumptions, fid) if assumptions is not None else ""

    repro_html = ""
    if f.get("repro"):
        repro_html = (
            f'<div class="section"><div class="section-label">Minimal repro</div>'
            f'{f["repro"]}</div>'
        )

    return (
        f'<div class="finding {sev}" id="{html.escape(f["id"], quote=True)}">'
        f'<div class="finding-head">'
        f'<span class="finding-id mono">{html.escape(f["id"])}</span>'
        f'{_copy_btn(f["id"])}'
        f'{"".join(badges)}'
        f'<span class="location">{html.escape(f["location"])}</span>'
        f'{_copy_btn(f["location"])}'
        f'</div>'
        f'{bluf_html}'
        f'{impact_html}'
        f'<div class="section"><div class="section-label">Description</div>'
        f'<div class="prose">{f["description"]}</div></div>'
        f'{assumptions_html}'
        f'{repro_html}'
        f'{snippets_html}'
        f'<div class="section"><div class="section-label">Recommended action</div>'
        f'<div class="prose">{f["action"]}</div></div>'
        f'</div>'
    )


def render_report(meta: dict, findings: list) -> str:
    """Render the full self-contained HTML report.

    meta: dict with reviewer, generated, pr, url, head_commit, base_branch
          (see the module docstring for the shape).
    findings: ordered list of finding dicts (see module docstring).
              Grouped by severity in the document; input order is
              preserved inside each group.
    """
    by_sev: dict = {s: [] for s in _SEVERITY_ORDER}
    for f in findings:
        by_sev[f["severity"].lower()].append(f)

    sections = []
    for sev in _SEVERITY_ORDER:
        if not by_sev[sev]:
            continue
        cards = "\n".join(_render_finding(f) for f in by_sev[sev])
        sections.append(f'<h2>{_SEVERITY_LABEL[sev]}</h2>\n{cards}')
    body = "\n".join(sections) or "<p><em>No findings.</em></p>"

    pr = meta["pr"]
    return (
        "<!DOCTYPE html>\n"
        f'<html lang="en"><head><meta charset="utf-8">'
        f'<title>PR #{pr} review</title>'
        f'<style>{_REPORT_CSS}\n{style_css()}</style>'
        f'<script>{_REPORT_JS}</script>'
        f'</head><body>'
        f'<h1>PR #{pr} review</h1>'
        f'{_render_meta(meta)}'
        f'{body}'
        f'</body></html>'
    )
