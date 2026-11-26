import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "prompts"))

import PR_RENDER as render


# ---------------------------------------------------------------------------
# Snippet layer.
# ---------------------------------------------------------------------------

def test_code_is_html_escaped():
    out = render.render_snippet('x := "<b>&amp;</b>"', lexer="go")
    assert "<b>" not in out
    assert "&lt;b&gt;" in out


def test_go_token_classes():
    out = render.render_snippet("func f() int { return 42 } // answer", lexer="go")
    assert '<span class="kw">func</span>' in out
    assert '<span class="kw">return</span>' in out
    assert '<span class="num">42</span>' in out
    assert '<span class="com">// answer</span>' in out


def test_go_string_token():
    out = render.render_snippet('s := "hi"', lexer="go")
    assert '<span class="str">&quot;hi&quot;</span>' in out


def test_comment_marker_inside_string_is_not_a_comment():
    out = render.render_snippet('u := "http://x"', lexer="go")
    assert '<span class="com">' not in out


def test_multiline_block_comment_spans_per_line():
    out = render.render_snippet("/*\nmid\n*/", lexer="go")
    assert '<span class="com">/*</span>' in out
    assert '<span class="com">mid</span>' in out
    assert '<span class="com">*/</span>' in out


def test_go_backtick_string_multiline():
    out = render.render_snippet("s := `a\nb`", lexer="go")
    assert '<span class="str">`a</span>' in out
    assert '<span class="str">b`</span>' in out


def test_python_triple_quoted_multiline():
    out = render.render_snippet('x = """a\nb"""', lexer="python")
    assert '<span class="str">&quot;&quot;&quot;a</span>' in out
    assert '<span class="str">b&quot;&quot;&quot;</span>' in out


def test_sql_keywords_case_insensitive():
    out = render.render_snippet("select * from t", lexer="sql")
    assert '<span class="kw">select</span>' in out
    assert '<span class="kw">from</span>' in out


def test_unknown_lexer_renders_plain_text():
    out = render.render_snippet("func x", lexer="no-such-lang")
    assert "func x" in out
    assert '<span class="kw">' not in out


def test_hl_lines_with_first_line_offset():
    out = render.render_snippet("a\nb\nc", lexer="text",
                                first_line=100, hl_lines=[101])
    assert out.count('<span class="hll">') == 1
    assert '<span class="hll">b\n</span>' in out


def test_gutter_starts_at_first_line():
    out = render.render_snippet("a\nb", lexer="text", first_line=7)
    assert "<pre>7\n8</pre>" in out


def test_from_file_line_range_and_lexer_guess(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text("# one\ndef two():\n    return 3\n")
    out = render.from_file(str(f), 2, 3)
    assert '<span class="kw">def</span>' in out
    assert "# one" not in out
    assert "<pre>2\n3</pre>" in out


# ---------------------------------------------------------------------------
# Scenario traces.
# ---------------------------------------------------------------------------

def test_trace_renders_numbered_steps_with_inline_code_and_arrows():
    out = render.render_trace(["run `tsh mcp login x`", "GetAuthHeader -> refresh"])
    assert out.startswith('<div class="trace">')
    assert out.count("<li>") == 2
    assert "<code>tsh mcp login x</code>" in out
    assert "GetAuthHeader → refresh" in out
    assert "->" not in out


def test_trace_escapes_html_in_prose_and_code():
    out = render.render_trace(["a <b>bold</b> `x < y`"])
    assert "<b>" not in out
    assert "&lt;b&gt;" in out
    assert "<code>x &lt; y</code>" in out


def test_trace_note_and_nested_steps():
    out = render.render_trace([("token expires", "no refresh token"),
                               ("request", ["probe -> 200", "return nil"])])
    assert '<span class="note">no refresh token</span>' in out
    assert out.count("<ol>") == 2
    assert "probe → 200" in out


def test_trace_preamble_and_outcome():
    out = render.render_trace(["s"], preamble="Source trace; not a cluster run.",
                              expected="header omitted", actual="login-required error")
    assert '<p class="trace-pre">Source trace; not a cluster run.</p>' in out
    assert '<span class="lbl exp">Expected</span><span>header omitted</span>' in out
    assert '<span class="lbl act">Actual</span><span>login-required error</span>' in out


def test_trace_without_outcome_omits_footer():
    out = render.render_trace(["s"])
    assert "trace-outcome" not in out
    assert "trace-pre" not in out


def test_trace_rejects_empty_and_malformed():
    import pytest
    with pytest.raises(ValueError, match="at least one step"):
        render.render_trace([])
    with pytest.raises(ValueError, match="trace step"):
        render.render_trace([("a", "b", "c")])


def test_trace_css_present_in_report():
    doc = render.render_report(meta=_META, findings=[_finding(repro=render.render_trace(["s"]))])
    assert ".trace ol" in doc
    assert ".lbl.exp" in doc
    assert 'class="trace"' in doc


# ---------------------------------------------------------------------------
# Sequence diagrams.
# ---------------------------------------------------------------------------

def test_sequence_is_inline_svg_with_participants_and_lifelines():
    out = render.render_sequence(["tsh", "server"], [("msg", "tsh", "server", "GET /mcp")])
    assert out.startswith('<div class="seq"><svg')
    assert "<svg" in out and "</svg>" in out
    assert out.count("stroke-dasharray=\"4 4\"") == 2  # one lifeline per participant
    assert ">tsh<" in out and ">server<" in out
    assert "GET /mcp" in out
    # Self-contained: no external references.
    assert "http://" not in out.replace("http://www.w3.org/2000/svg", "")
    assert "<script" not in out


def test_sequence_message_kinds_and_markers():
    out = render.render_sequence(["a", "b"], [
        ("msg", "a", "b", "call"),
        ("msg", "b", "a", "reply", "reply"),
        ("msg", "a", "b", "leak", "danger"),
        ("msg", "b", "a", "denied", "fail"),
    ])
    assert out.count('stroke="#e74c3c"') == 2  # danger and fail lines
    assert out.count('fill="#e74c3c"') == 1    # the red arrowhead marker
    assert out.count('stroke-dasharray="6 4"') == 2  # reply and fail
    assert "-d)" in out and "-n)" in out  # both markers referenced


def test_sequence_self_message_note_and_mark():
    out = render.render_sequence(["a", "b"], [
        ("mark", "t = 60 s"),
        ("msg", "a", "a", "cache hit"),
        ("note", ["a", "b"], "two\nlines"),
    ])
    assert "t = 60 s" in out
    assert "cache hit" in out
    assert "<path d=" in out  # self message loop
    assert 'fill="#2a2d23"' in out  # note box
    assert ">two<" in out and ">lines<" in out


def test_sequence_labels_escaped_and_backticks_monospace():
    out = render.render_sequence(["a", "b"], [("msg", "a", "b", "send `<tok>` & go")])
    assert "<tok>" not in out
    assert "&lt;tok&gt;" in out
    assert 'font-family="ui-monospace' in out
    assert "&amp; go" in out


def test_sequence_caption_and_errors():
    import pytest
    out = render.render_sequence(["a"], [("mark", "x")], caption="Not a `live` run.")
    assert '<p class="seq-caption">Not a <code>live</code> run.</p>' in out
    with pytest.raises(ValueError, match="unknown participant 'zz'"):
        render.render_sequence(["a"], [("msg", "a", "zz", "x")])
    with pytest.raises(ValueError, match="unknown message kind"):
        render.render_sequence(["a"], [("msg", "a", "a", "x", "wavy")])
    with pytest.raises(ValueError, match="unknown event kind"):
        render.render_sequence(["a"], [("loop", "x")])
    with pytest.raises(ValueError, match="at least one"):
        render.render_sequence([], [("mark", "x")])
    with pytest.raises(ValueError, match="at least one"):
        render.render_sequence(["a"], [])


def test_sequence_marker_ids_unique_per_diagram():
    a = render.render_sequence(["a", "b"], [("msg", "a", "b", "x")])
    b = render.render_sequence(["a", "b"], [("msg", "a", "b", "x")])
    ida = a.split('<marker id="')[1].split('"')[0]
    idb = b.split('<marker id="')[1].split('"')[0]
    assert ida != idb


def test_sequence_in_report_stays_self_contained():
    doc = render.render_report(meta=_META, findings=[_finding(
        repro=render.render_sequence(["a", "b"], [("msg", "a", "b", "x")]))])
    assert 'class="seq"' in doc
    assert "<link" not in doc
    assert "src=" not in doc
    assert ".seq svg" in doc


# ---------------------------------------------------------------------------
# Full report.
# ---------------------------------------------------------------------------

_META = {
    "reviewer": "test-model",
    "generated": "2026-06-10T00:00:00+00:00",
    "pr": 1,
    "url": "https://github.com/o/r/pull/1",
    "head_commit": "abc123",
    "base_branch": "master",
}


def _finding(**over):
    f = {
        "id": "1-test-finding",
        "severity": "high",
        "location": "lib/a.go:10",
        "category": "a",
        "rule": "R2",
        "impact": "<p>users see X</p>",
        "description": "<p>desc</p>",
        "assumptions": _ASSUMPTIONS,
        "action": "<p>act</p>",
        "snippets": [render.render_snippet("x := 1", lexer="go", first_line=10)],
    }
    f.update(over)
    return f


_ASSUMPTIONS = {
    "rows": [
        ("An admin repoints the app", "low", "privileged and audited"),
        ("A session is live in the window", "high", "clients run for hours"),
    ],
    "overall": ("low-to-medium", "weakest link is the admin action"),
}


def test_render_report_smoke():
    doc = render.render_report(
        meta={
            "reviewer": "test-model",
            "generated": "2026-06-10T00:00:00+00:00",
            "pr": 1,
            "url": "https://github.com/o/r/pull/1",
            "head_commit": "abc123",
            "base_branch": "master",
        },
        findings=[_finding(), _finding(id="2-low-thing", severity="low", rule=None)],
    )
    assert doc.startswith("<!DOCTYPE html>")
    assert "<h2>High</h2>" in doc
    assert "<h2>Low</h2>" in doc
    assert "1-test-finding" in doc
    assert "2-low-thing" in doc
    assert "badge rule" in doc
    # Self-contained: nothing loaded from the network.
    assert "<link" not in doc
    assert "src=" not in doc


def test_finding_renders_bluf_before_description():
    doc = render.render_report(
        meta=_META,
        findings=[_finding(bluf="Auth bypass: Authorize never checks ctx")],
    )
    assert 'class="bluf"' in doc
    assert "Auth bypass: Authorize never checks ctx" in doc
    # BLUF leads the finding -- it sits above the Description label.
    assert doc.index('class="bluf"') < doc.index(">Description<")


def test_finding_without_bluf_omits_it():
    doc = render.render_report(meta=_META, findings=[_finding()])
    assert 'class="bluf"' not in doc


def test_finding_renders_minimal_repro_section():
    doc = render.render_report(
        meta=_META,
        findings=[_finding(repro="<ol><li>call Authorize(nil)</li></ol>")],
    )
    assert "Minimal repro" in doc
    assert "call Authorize(nil)" in doc


def test_finding_without_repro_omits_section():
    doc = render.render_report(meta=_META, findings=[_finding()])
    assert "Minimal repro" not in doc


# ---------------------------------------------------------------------------
# User impact and threat-model assumptions.
# ---------------------------------------------------------------------------

def test_impact_renders_between_bluf_and_description():
    doc = render.render_report(
        meta=_META,
        findings=[_finding(bluf="Auth bypass", impact="<p>every login is refused</p>")],
    )
    assert 'class="impact"' in doc
    assert ">User impact<" in doc
    assert "every login is refused" in doc
    assert doc.index('class="bluf"') < doc.index('class="impact"') < doc.index(">Description<")


def test_missing_impact_raises():
    import pytest
    for bad in ({"impact": None}, {"impact": ""}, {"impact": "   "}):
        with pytest.raises(ValueError, match="impact"):
            render.render_report(meta=_META, findings=[_finding(**bad)])


def test_finding_without_impact_key_raises():
    import pytest
    f = _finding()
    del f["impact"]
    with pytest.raises(ValueError, match="impact"):
        render.render_report(meta=_META, findings=[f])


def test_assumptions_table_renders_rows_and_overall():
    doc = render.render_report(meta=_META, findings=[_finding()])
    assert 'class="assumptions"' in doc
    assert "Threat-model assumptions" in doc
    assert "An admin repoints the app" in doc
    assert "clients run for hours" in doc
    assert '<span class="lk low">Low</span>' in doc
    assert '<span class="lk high">High</span>' in doc
    assert 'class="overall"' in doc
    assert "Combined likelihood" in doc
    assert '<span class="lk low-to-medium">Low to medium</span>' in doc
    # Table follows the description and precedes the repro.
    assert doc.index(">Description<") < doc.index('class="assumptions"')


def test_assumptions_table_precedes_repro():
    doc = render.render_report(meta=_META, findings=[_finding(repro="<p>rp</p>")])
    assert doc.index('class="assumptions"') < doc.index("Minimal repro")


def test_unknown_likelihood_raises():
    import pytest
    bad = {"rows": [("a", "probably", "b")], "overall": ("low", "x")}
    with pytest.raises(ValueError, match="unknown likelihood 'probably'"):
        render.render_report(meta=_META, findings=[_finding(assumptions=bad)])
    bad = {"rows": [("a", "low", "b")], "overall": ("certain", "x")}
    with pytest.raises(ValueError, match="unknown likelihood 'certain'"):
        render.render_report(meta=_META, findings=[_finding(assumptions=bad)])


def test_malformed_assumptions_raise():
    import pytest
    with pytest.raises(ValueError, match="rows is empty"):
        render.render_report(meta=_META, findings=[_finding(assumptions={"rows": [], "overall": ("low", "x")})])
    with pytest.raises(ValueError, match="assumption, likelihood, rationale"):
        render.render_report(meta=_META, findings=[_finding(assumptions={"rows": [("a", "low")], "overall": ("low", "x")})])
    with pytest.raises(ValueError, match="overall"):
        render.render_report(meta=_META, findings=[_finding(assumptions={"rows": [("a", "low", "b")]})])


def test_assumptions_required_for_medium_and_above():
    import pytest
    for sev in ("blocker", "high", "medium"):
        with pytest.raises(ValueError, match="assumptions"):
            render.render_report(meta=_META, findings=[_finding(severity=sev, assumptions=None)])


def test_assumptions_optional_for_low_and_nit():
    for sev in ("low", "nit"):
        doc = render.render_report(meta=_META, findings=[_finding(severity=sev, assumptions=None)])
        assert 'class="assumptions"' not in doc
        assert "users see X" in doc  # impact still mandatory and rendered


def test_likelihood_scale_is_exported_and_styled():
    doc = render.render_report(meta=_META, findings=[_finding()])
    assert render.LIKELIHOODS == ("very-low", "low", "low-to-medium", "medium", "high")
    for lk in render.LIKELIHOODS:
        assert f".lk.{lk}" in doc


def test_two_tier_width_prose_capped_container_wide():
    doc = render.render_report(meta=_META, findings=[_finding()])
    assert "max-width: 80rem" in doc
    # One shared edge and size for all text blocks, including the table.
    assert ".prose, .impact, .bluf, .assumptions table {" in doc
    assert "max-width: var(--text-width);" in doc
    assert "font-size: var(--text-size);" in doc
    # Description and action are prose; snippets and tables are not wrapped.
    assert '<div class="prose"><p>desc</p></div>' in doc
    assert '<div class="prose"><p>act</p></div>' in doc
    assert doc.count('class="prose"') == 2


def test_report_mandates_dark_theme():
    doc = render.render_report(meta=_META, findings=[_finding()])
    # Dark is mandated, not merely offered: the OS light preference is
    # overridden and no light color-scheme survives anywhere.
    assert "color-scheme: dark" in doc
    assert "color-scheme: light" not in doc
