import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import prco


def test_repo_slug_plain():
    assert prco.repo_slug("https://github.com/gravitational/teleport") == "gravitational/teleport"


def test_repo_slug_strips_git_and_slash():
    assert prco.repo_slug("https://github.com/gravitational/rfd.git") == "gravitational/rfd"
    assert prco.repo_slug("https://github.com/gravitational/rfd/") == "gravitational/rfd"


def test_repo_name():
    assert prco.repo_name("https://github.com/gravitational/teleport") == "teleport"
    assert prco.repo_name("https://github.com/gravitational/rfd.git") == "rfd"


def test_parse_pr_url_valid():
    assert prco.parse_pr_url("https://github.com/gravitational/rfd/pull/18") == ("gravitational/rfd", 18)


def test_parse_pr_url_trailing_path():
    assert prco.parse_pr_url("https://github.com/gravitational/rfd/pull/18/files") == ("gravitational/rfd", 18)


def test_parse_pr_url_not_a_url():
    assert prco.parse_pr_url("18") is None


def test_parse_pr_url_repo_root():
    assert prco.parse_pr_url("https://github.com/gravitational/rfd") is None


def test_load_config_parses_repos(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[[repo]]\n'
        'clone = "~/code/teleport"\n'
        'url = "https://github.com/gravitational/teleport"\n'
        'setup = "rm -f AGENTS.md"\n'
        'teardown = "git restore AGENTS.md"\n'
        '\n'
        '[[repo]]\n'
        'clone = "~/code/rfd"\n'
        'url = "https://github.com/gravitational/rfd"\n'
    )
    repos = prco.load_config(cfg)
    assert len(repos) == 2
    first = repos[0]
    assert first.slug == "gravitational/teleport"
    assert first.name == "teleport"
    assert first.clone == Path("~/code/teleport").expanduser()
    assert first.setup == "rm -f AGENTS.md"
    assert first.teardown == "git restore AGENTS.md"
    assert repos[1].setup is None
    assert repos[1].teardown is None


def test_load_config_missing_file(tmp_path):
    assert prco.load_config(tmp_path / "nope.toml") is None


def test_load_config_empty(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("")
    assert prco.load_config(cfg) == []


def _repos():
    return [
        prco.Repo.from_toml({"clone": "~/code/teleport", "url": "https://github.com/gravitational/teleport"}),
        prco.Repo.from_toml({"clone": "~/code/rfd", "url": "https://github.com/gravitational/rfd"}),
    ]


def test_resolve_bare_number_uses_default():
    repo, pr = prco.resolve_target("18", _repos())
    assert repo.name == "teleport"
    assert pr == 18


def test_resolve_url_matches_repo():
    repo, pr = prco.resolve_target("https://github.com/gravitational/rfd/pull/18", _repos())
    assert repo.name == "rfd"
    assert pr == 18


def test_resolve_url_match_is_case_insensitive():
    repo, pr = prco.resolve_target("https://github.com/Gravitational/RFD/pull/7", _repos())
    assert repo.name == "rfd"
    assert pr == 7


def test_resolve_url_no_match_raises():
    import pytest
    with pytest.raises(prco.ConfigError):
        prco.resolve_target("https://github.com/other/thing/pull/1", _repos())


def test_resolve_bare_number_no_default_raises():
    import pytest
    with pytest.raises(prco.ConfigError):
        prco.resolve_target("18", [])


def test_resolve_garbage_raises():
    import pytest
    with pytest.raises(prco.ConfigError):
        prco.resolve_target("not-a-pr", _repos())


def test_worktree_path():
    repo = prco.Repo.from_toml({"clone": "~/code/rfd", "url": "https://github.com/gravitational/rfd"})
    assert prco.worktree_path(repo, 18) == Path("~/code").expanduser() / "rfd-pr-18"


def test_remove_script_without_teardown():
    # Paths with a space exercise shlex.quote's quoting.
    script = prco.make_remove_script(
        Path("/c d"), Path("/c d/rfd-pr-18"), [Path("/c d/rfd-pr-18/PR_INFO.txt")]
    )
    assert "git worktree remove '/c d/rfd-pr-18'" in script
    assert "rm -- '/c d/rfd-pr-18/PR_INFO.txt'" in script
    assert "git restore" not in script


def test_remove_script_with_teardown():
    script = prco.make_remove_script(
        Path("/c"), Path("/c/teleport-pr-1"), [Path("/c/teleport-pr-1/PR_INFO.txt")],
        teardown="git restore AGENTS.md",
    )
    # No special chars -> shlex.quote leaves the path bare.
    assert "( cd /c/teleport-pr-1 && git restore AGENTS.md )" in script
    assert "git worktree remove /c/teleport-pr-1" in script


def test_config_template_is_valid_toml_with_repo():
    import tomllib
    data = tomllib.loads(prco.config_template())
    assert "repo" in data
    assert isinstance(data["repo"], list) and len(data["repo"]) >= 1
    assert data["repo"][0]["url"].startswith("https://github.com/")


def test_format_review_template_renders():
    # The template goes through str.format(); a stray { or } added to
    # it (e.g. writing {suffix} instead of <suffix>) blows up here.
    meta = {
        "title": "T",
        "author": {"login": "a"},
        "url": "u",
        "headRefName": "h",
        "baseRefName": "b",
    }
    text = prco.format_review(meta, 7, "o/r")
    assert "pull request #7 from o/r" in text
    assert "PR_7.diff" in text


def test_format_description():
    meta = {"number": 7, "title": "T", "body": "  Why.\n\n- a {b}\n"}
    assert prco.format_description(meta) == "# PR #7: T\n\nWhy.\n\n- a {b}\n"


def test_format_description_empty_body():
    meta = {"number": 7, "title": "T", "body": ""}
    assert prco.format_description(meta) == "# PR #7: T\n\n(no description)\n"


PORCELAIN = (
    "worktree /c/teleport\n"
    "HEAD 1111111111111111111111111111111111111111\n"
    "branch refs/heads/master\n"
    "\n"
    "worktree /c/teleport-pr-1\n"
    "HEAD 2222222222222222222222222222222222222222\n"
    "detached\n"
    "\n"
    "worktree /c/teleport-pr-2\n"
    "HEAD 3333333333333333333333333333333333333333\n"
    "branch refs/heads/feat/x\n"
    "\n"
)


def test_parse_worktree_list():
    entries = prco.parse_worktree_list(PORCELAIN)
    assert entries == [
        prco.Worktree(Path("/c/teleport"), "master"),
        prco.Worktree(Path("/c/teleport-pr-1"), None),
        prco.Worktree(Path("/c/teleport-pr-2"), "feat/x"),
    ]


def test_worktree_holding_branch():
    entries = prco.parse_worktree_list(PORCELAIN)
    assert prco.worktree_holding(entries, "feat/x") == Path("/c/teleport-pr-2")
    assert prco.worktree_holding(entries, "nope") is None


def test_worktree_at_path():
    entries = prco.parse_worktree_list(PORCELAIN)
    assert prco.worktree_at(entries, Path("/c/teleport-pr-1")) == prco.Worktree(Path("/c/teleport-pr-1"), None)
    assert prco.worktree_at(entries, Path("/c/other")) is None


def test_suffixed_worktree_path():
    import datetime
    repo = prco.Repo.from_toml({"clone": "~/code/rfd", "url": "https://github.com/gravitational/rfd"})
    now = datetime.datetime(2026, 9, 3, 9, 41, 7)
    assert prco.suffixed_worktree_path(repo, 18, now) == Path("~/code").expanduser() / "rfd-pr-18-20260903-094107"


def test_update_check_accepts_detached_or_pr_branch():
    entries = prco.parse_worktree_list(PORCELAIN)
    assert prco.update_problem(entries, Path("/c/teleport-pr-1"), "feat/x") is None
    assert prco.update_problem(entries, Path("/c/teleport-pr-2"), "feat/x") is None


def test_update_check_rejects_other_branch_and_non_worktree():
    entries = prco.parse_worktree_list(PORCELAIN)
    assert "master" in prco.update_problem(entries, Path("/c/teleport"), "feat/x")
    assert "not a worktree" in prco.update_problem(entries, Path("/c/stray"), "feat/x")


def test_conflict_message_lists_both_reruns():
    # Under pytest stderr is not a TTY, so the palette is plain text.
    msg = prco.conflict_message(Path("/c/rfd-pr-18"), "18")
    assert "/c/rfd-pr-18 already exists" in msg
    assert "\n    prco --update 18\n" in msg
    assert "\n    prco --suffix 18\n" in msg


def test_open_editor_uses_visual(monkeypatch, tmp_path):
    calls = {}
    monkeypatch.setenv("VISUAL", "myeditor")
    monkeypatch.setenv("EDITOR", "vi")

    def fake_run(args, check):
        calls["args"] = args
    monkeypatch.setattr(prco.subprocess, "run", fake_run)

    target = tmp_path / "config.toml"
    prco.open_editor(target)
    assert calls["args"] == ["myeditor", str(target)]


class _FakeResult:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


def test_prism_running_true_when_alive(monkeypatch):
    def fake_run(args, **kwargs):
        assert args == ["prism", "status"]
        return _FakeResult(0, "Router:      127.0.0.1:7331  [alive (pid 1)]\n")
    monkeypatch.setattr(prco.subprocess, "run", fake_run)
    assert prco.prism_running() is True


def test_prism_running_false_when_down(monkeypatch):
    def fake_run(args, **kwargs):
        return _FakeResult(1, "Router:      not running\n")
    monkeypatch.setattr(prco.subprocess, "run", fake_run)
    assert prco.prism_running() is False


def test_prism_running_false_when_not_installed(monkeypatch):
    def fake_run(args, **kwargs):
        raise FileNotFoundError
    monkeypatch.setattr(prco.subprocess, "run", fake_run)
    assert prco.prism_running() is False


def test_agent_commands_claude_only_without_prism_or_codex(monkeypatch):
    monkeypatch.setattr(prco.shutil, "which", lambda name: None)
    assert prco.agent_commands() == ["claude"]


def test_agent_commands_adds_codex_when_installed(monkeypatch):
    monkeypatch.setattr(prco.shutil, "which",
                         lambda name: "/usr/bin/codex" if name == "codex" else None)
    assert prco.agent_commands() == ["claude", "codex"]


def test_agent_commands_adds_prism_variants_when_router_up(monkeypatch):
    monkeypatch.setattr(prco.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(prco, "prism_running", lambda: True)
    assert prco.agent_commands() == ["claude", "prism claude", "codex", "prism codex"]


def test_agent_commands_skips_prism_variants_when_router_down(monkeypatch):
    monkeypatch.setattr(prco.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(prco, "prism_running", lambda: False)
    assert prco.agent_commands() == ["claude", "codex"]
