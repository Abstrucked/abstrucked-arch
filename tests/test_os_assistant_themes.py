"""Theme integration never touches the host desktop; helpers live in fixtures."""

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "os-assistant/.local/share/os-assistant"))

from os_assistant.config import Config, load_config
from os_assistant.contracts import AssistantError, PolicyError, PreparedCall
from os_assistant.policy import Policy, tool_schemas
from os_assistant.runner import Runner, run_captured, theme_environment
from os_assistant import themes
import os_assistant.runner as execution


@pytest.fixture
def theme_repo(tmp_path, monkeypatch):
    repo = tmp_path / "checkout"
    for name in ("themes/palettes/nord.lua", "themes/palettes/mocha-peach.lua",
                 "themes/palettes/_defaults.lua", "themes/render.lua", "themes/targets.conf",
                 "themes/templates/theme.tpl", "themes/hooks/fake.sh", "plugins/pluginctl",
                 "scripts/config_syntax.py", "scripts/.local/bin/display-detect",
                 "awesome/.config/awesome/theme-layout.lua", "awesome/.config/awesome/theme-session.lua",
                 "awesome/.config/awesome/themes/mono/theme.lua",
                 "awesome/.config/awesome/themes/powerarrow/theme.lua"):
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture\n")
    helper = repo / "themes/themectl"
    helper.write_text('#!/bin/sh\nif [ "$1" = current ]; then\n'
                      '  if [ "$#" -gt 1 ]; then echo nord; else echo mono; fi\n'
                      'else echo "fixture change requested"; fi\n')
    helper.chmod(0o755)
    monkeypatch.setattr(themes, "THEME_ROOT", repo / "themes")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home/.config"))
    monkeypatch.delenv("AWESOME_THEME", raising=False)
    return repo


def policy():
    return Policy(Config(themes_enabled=True, actions_enabled=True))


def test_theme_tools_need_explicit_opt_in(theme_repo):
    names = lambda config: {item["function"]["name"] for item in tool_schemas(config)}
    assert "theme_status" not in names(Config(actions_enabled=True))
    assert "set_theme" not in names(Config())
    assert "theme_status" in names(Config(themes_enabled=True))
    assert "set_theme" not in names(Config(themes_enabled=True))
    assert {"theme_status", "set_theme"} <= names(Config(themes_enabled=True, actions_enabled=True))
    # apply_theme re-renders/reloads the current palette; it is gated on BOTH opt-ins.
    assert "apply_theme" not in names(Config())
    assert "apply_theme" not in names(Config(themes_enabled=True))
    assert "apply_theme" not in names(Config(actions_enabled=True))
    assert "apply_theme" in names(Config(themes_enabled=True, actions_enabled=True))
    with pytest.raises(PolicyError):
        Policy(Config(actions_enabled=True)).prepare("set_theme", {"palette": "nord"})
    with pytest.raises(PolicyError):
        Policy(Config(themes_enabled=True)).prepare("apply_theme", {})
    with pytest.raises(PolicyError):
        Policy(Config(actions_enabled=True)).prepare("apply_theme", {})


def test_catalogue_is_metadata_only_and_names_are_enumerated(theme_repo, monkeypatch):
    monkeypatch.setattr(execution.subprocess, "Popen", lambda *a, **kw: pytest.fail("Catalogue executed a helper"))
    assert themes.catalogue() == {"layouts": ["mono", "powerarrow"], "palettes": ["mocha-peach", "nord"]}
    schemas = {item["function"]["name"]: item["function"] for item in tool_schemas(Config(themes_enabled=True, actions_enabled=True))}
    assert schemas["set_theme"]["parameters"]["properties"]["palette"]["enum"] == ["mocha-peach", "nord"]


@pytest.mark.parametrize("arguments,tail", [
    ({"palette": "nord"}, ("set", "--colors", "nord")),
    ({"layout": "mono"}, ("set", "mono")),
    ({"palette": "nord", "layout": "mono"}, ("set", "mono", "--colors", "nord")),
])
def test_exact_theme_argv_is_frozen(theme_repo, arguments, tail):
    call = policy().prepare("set_theme", arguments)
    assert call.argv == (str(theme_repo / "themes/themectl"), *tail)
    assert call.mutates and len(call.verification) == 64


@pytest.mark.parametrize("arguments", [
    {}, {"palette": "unknown"}, {"palette": "--help"}, {"layout": "../../outside"},
    {"layout": "mono", "palette": ""},
    {"palette": "nord;touch marker"}, {"palette": "$(whoami)"}, {"palette": "nord\n"},
    {"palette": None}, {"palette": True}, {"layout": "mono", "command": "apply"},
    {"palette": "nord", "helper": "/bin/sh"}, {"colors": "#123456"},
])
def test_unsupported_theme_arguments_never_execute(theme_repo, arguments, monkeypatch):
    monkeypatch.setattr(execution.subprocess, "Popen", lambda *a, **kw: pytest.fail("Invalid proposal executed"))
    with pytest.raises(PolicyError):
        policy().prepare("set_theme", arguments)


def test_theme_dry_run_neither_executes_nor_approves(theme_repo, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Dry-run executed a helper or requested approval")
    monkeypatch.setattr(execution.subprocess, "Popen", forbidden)
    runner = Runner(policy(), dry_run=True, confirm=forbidden)
    for name, arguments in (("set_theme", {"palette": "nord"}), ("theme_status", {})):
        call = runner.policy.prepare(name, arguments)
        result = runner.run(call)
        assert result.status == "preview"
        assert result.data["argv"] == list(call.argv)
    assert not (theme_repo / "themes/out").exists()
    assert not (theme_repo / "themes/.generations").exists()


def test_theme_denial_never_runs_helper(theme_repo, monkeypatch):
    monkeypatch.setattr(execution.subprocess, "Popen", lambda *a, **kw: pytest.fail("Denied helper executed"))
    runner = Runner(policy())
    result = runner.run(runner.policy.prepare("set_theme", {"palette": "nord"}))
    assert result.status == "denied"


def test_theme_status_uses_only_fixed_current_commands(theme_repo, monkeypatch):
    calls = []

    def capture(argv, timeout, *, environment):
        calls.append(argv)
        assert 0 < timeout <= 5 and environment["PATH"] == "/usr/bin:/bin"
        return (0, "nord\n" if "--colors" in argv else "mono\n", "")

    monkeypatch.setattr(execution, "run_captured", capture)
    runner = Runner(policy(), confirm=lambda call: pytest.fail("Read-only status requested approval"))
    result = runner.run(runner.policy.prepare("theme_status", {}))
    assert result.status == "ok"
    assert result.data["current_layout"] == "mono" and result.data["current_palette"] == "nord"
    assert calls == [(str(theme_repo / "themes/themectl"), "current"),
                     (str(theme_repo / "themes/themectl"), "current", "--colors")]


def test_fixture_status_can_execute_without_host_desktop(theme_repo):
    runner = Runner(policy())
    result = runner.run(runner.policy.prepare("theme_status", {}))
    assert result.data["current_layout"] == "mono" and result.data["current_palette"] == "nord"


def test_unexpected_theme_state_contents_are_not_exposed(theme_repo, monkeypatch):
    monkeypatch.setattr(execution, "run_captured", lambda *a, **kw: (0, "fixture-private-unexpected-value\n", ""))
    runner = Runner(policy())
    result = runner.run(runner.policy.prepare("theme_status", {}))
    assert result.data["current_layout"] == "unavailable"
    assert "fixture-private" not in repr(result.data)


@pytest.mark.parametrize("code,warning,status", [(0, "", "ok"), (0, "hook failed", "error"), (1, "", "error")])
def test_theme_changes_report_warnings_and_do_not_claim_desktop_verification(theme_repo, monkeypatch, code, warning, status):
    calls, approvals = [], []

    def capture(argv, timeout, *, environment):
        calls.append(argv)
        assert timeout == 120
        return code, "palette: nord\n", warning

    monkeypatch.setattr(execution, "run_captured", capture)
    runner = Runner(policy(), confirm=lambda call: approvals.append(call) or True)
    call = runner.policy.prepare("set_theme", {"palette": "nord"})
    result = runner.run(call)
    assert result.status == status
    assert result.data["desktop_verified"] is False
    assert result.data["warnings"] == warning
    assert len(calls) == len(approvals) == 1
    if status == "error":
        assert "may already have been applied" in result.data["message"]


@pytest.mark.parametrize("failure", [AssistantError("fixture timeout"), OSError("fixture output failure")])
def test_theme_timeout_or_io_error_warns_about_partial_changes(theme_repo, monkeypatch, failure):
    def failed(*args, **kwargs):
        raise failure
    monkeypatch.setattr(execution, "run_captured", failed)
    runner = Runner(policy(), confirm=lambda call: True)
    result = runner.run(runner.policy.prepare("set_theme", {"palette": "nord"}))
    assert result.status == "error" and "may already have been applied" in result.data["message"]


def test_model_cannot_retry_theme_hook_warning(theme_repo, monkeypatch):
    from os_assistant.agent import Agent

    class Client:
        requests = 0

        def chat(self, messages, tools):
            self.requests += 1
            assert self.requests == 1, "Model retried a partially applied theme"
            return {"message": {"content": "", "tool_calls": [
                {"function": {"name": "set_theme", "arguments": {"palette": "nord"}}},
            ]}}

    monkeypatch.setattr(execution, "run_captured", lambda *a, **kw: (0, "palette: nord", "fixture hook warning"))
    agent = Agent(Client(), Runner(policy(), confirm=lambda call: True))
    assert "Stopped" in agent.ask("Change the palette to nord")
    assert agent.last_status == "error" and len(agent.last_results) == 1


# ---------------------------------------------------------------------------
# apply_theme: re-renders/reloads the CURRENT color palette.
# It never switches the desktop layout or changes any selection, takes no model
# arguments, and follows the exact set_theme trust/approval safety pattern.
# ---------------------------------------------------------------------------

def test_apply_theme_schema_takes_no_model_arguments(theme_repo):
    schemas = {item["function"]["name"]: item["function"] for item in
               tool_schemas(Config(themes_enabled=True, actions_enabled=True))}
    parameters = schemas["apply_theme"]["parameters"]
    assert parameters["properties"] == {}
    assert parameters["required"] == []
    assert parameters["additionalProperties"] is False
    call = policy().prepare("apply_theme", {})
    assert call.argument_dict() == {}


@pytest.mark.parametrize("arguments", [
    {"palette": "nord"}, {"layout": "mono"}, {"layout": "mono", "palette": "nord"},
    {"command": "apply"}, {"helper": "/bin/sh"}, {"root": "/etc"}, {"flags": "--force"},
    {"argv": ["/bin/sh"]}, {"mutates": True}, {"approved": True}, {"app": "editor"},
    {"percent": 50}, {"theme": "nord"}, {"colors": "#123456"},
])
def test_apply_theme_rejects_arbitrary_arguments(theme_repo, arguments, monkeypatch):
    monkeypatch.setattr(execution.subprocess, "Popen",
                        lambda *a, **kw: pytest.fail("Invalid apply proposal executed"))
    with pytest.raises(PolicyError):
        policy().prepare("apply_theme", arguments)


@pytest.mark.parametrize("arguments", [None, [], "apply", 42, 3.5, "x", {1: 2}])
def test_apply_theme_rejects_malformed_arguments(theme_repo, arguments, monkeypatch):
    monkeypatch.setattr(execution.subprocess, "Popen",
                        lambda *a, **kw: pytest.fail("Malformed apply proposal executed"))
    with pytest.raises(PolicyError):
        policy().prepare("apply_theme", arguments)


def test_exact_apply_theme_argv_is_frozen(theme_repo):
    call = policy().prepare("apply_theme", {})
    assert call.argv == (str(theme_repo / "themes/themectl"), "apply")
    assert call.mutates is True
    # Identical source-verification snapshot safety pattern to set_theme.
    assert len(call.verification) == 64
    assert call.verification == themes.snapshot()
    assert call.verification == policy().prepare("set_theme", {"palette": "nord"}).verification


def test_apply_theme_dry_run_neither_executes_nor_approves(theme_repo, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("apply_theme dry-run executed a helper or requested approval")
    monkeypatch.setattr(execution.subprocess, "Popen", forbidden)
    runner = Runner(policy(), dry_run=True, confirm=forbidden)
    call = runner.policy.prepare("apply_theme", {})
    result = runner.run(call)
    assert result.status == "preview"
    assert result.data["argv"] == list(call.argv)
    assert result.data["arguments"] == {}
    assert not (theme_repo / "themes/out").exists()
    assert not (theme_repo / "themes/.generations").exists()


def test_apply_theme_denial_never_runs_helper(theme_repo, monkeypatch):
    monkeypatch.setattr(execution.subprocess, "Popen",
                        lambda *a, **kw: pytest.fail("Denied apply executed"))
    runner = Runner(policy())
    result = runner.run(runner.policy.prepare("apply_theme", {}))
    assert result.status == "denied"


def test_apply_theme_requires_exact_per_call_approval(theme_repo, monkeypatch):
    calls, approvals = [], []

    def capture(argv, timeout, *, environment):
        calls.append(argv)
        return (0, "", "")

    monkeypatch.setattr(execution, "run_captured", capture)
    runner = Runner(policy(), confirm=lambda call: approvals.append(call) or True)
    first = runner.policy.prepare("apply_theme", {})
    second = runner.policy.prepare("apply_theme", {})
    assert runner.run(first).status == "ok"
    assert runner.run(second).status == "ok"
    assert approvals == [first, second]  # one exact approval per call, never reused
    assert calls == [first.argv, second.argv]


def test_apply_theme_forged_call_cannot_bypass_approval(theme_repo, monkeypatch):
    monkeypatch.setattr(execution.subprocess, "Popen",
                        lambda *a, **kw: pytest.fail("Forged apply executed"))
    runner = Runner(policy(), confirm=lambda call: True)
    forged = PreparedCall("apply_theme", (), True, ("/bin/sh", "apply"), "0" * 64)
    with pytest.raises(PolicyError):
        runner.run(forged)


def test_apply_theme_preview_discloses_side_effects_and_no_selection_change(theme_repo):
    import io
    from os_assistant.presentation import render_preview
    output = io.StringIO()
    render_preview(policy().prepare("apply_theme", {}), output)
    text = output.getvalue()
    assert "arguments: (none)" in text  # re-renders the current palette; changes no selection
    assert "app configurations" in text and "restart desktop" in text


@pytest.mark.parametrize("stage", ["before_run", "during_approval"])
def test_apply_theme_source_changes_invalidate_frozen_action(theme_repo, monkeypatch, stage):
    runner = Runner(policy())
    call = runner.policy.prepare("apply_theme", {})
    hook = theme_repo / "themes/hooks/fake.sh"
    monkeypatch.setattr(execution.subprocess, "Popen",
                        lambda *a, **kw: pytest.fail("Changed pipeline executed"))
    if stage == "before_run":
        hook.write_text("changed fixture\n")
        runner.confirm = lambda call: pytest.fail("Changed pipeline requested approval")
    else:
        def approve(call):
            hook.write_text("changed fixture\n")
            return True
        runner.confirm = approve
    with pytest.raises(PolicyError, match="changed"):
        runner.run(call)


@pytest.mark.parametrize("code,warning,status", [(0, "", "ok"), (0, "hook failed", "error"), (1, "", "error")])
def test_apply_theme_reports_errors_without_false_visual_success(theme_repo, monkeypatch, code, warning, status):
    calls, approvals = [], []

    def capture(argv, timeout, *, environment):
        calls.append(argv)
        assert timeout == 120
        return code, "palette: nord\n", warning

    monkeypatch.setattr(execution, "run_captured", capture)
    runner = Runner(policy(), confirm=lambda call: approvals.append(call) or True)
    call = runner.policy.prepare("apply_theme", {})
    result = runner.run(call)
    assert result.status == status
    assert result.data["desktop_verified"] is False
    assert result.data["warnings"] == warning
    assert result.data["selected"] == {}
    assert len(calls) == len(approvals) == 1
    if status == "error":
        assert "may already have been applied" in result.data["message"]
    else:
        assert "not verified" in result.data["message"]


@pytest.mark.parametrize("failure", [AssistantError("fixture timeout"), OSError("fixture output failure")])
def test_apply_theme_timeout_or_io_error_warns_about_partial_changes(theme_repo, monkeypatch, failure):
    def failed(*args, **kwargs):
        raise failure
    monkeypatch.setattr(execution, "run_captured", failed)
    runner = Runner(policy(), confirm=lambda call: True)
    result = runner.run(runner.policy.prepare("apply_theme", {}))
    assert result.status == "error" and "may already have been applied" in result.data["message"]


def test_model_cannot_retry_apply_theme_warning(theme_repo, monkeypatch):
    from os_assistant.agent import Agent

    class Client:
        requests = 0

        def chat(self, messages, tools):
            self.requests += 1
            assert self.requests == 1, "Model retried a partially applied theme"
            return {"message": {"content": "", "tool_calls": [
                {"function": {"name": "apply_theme", "arguments": {}}},
            ]}}

    monkeypatch.setattr(execution, "run_captured", lambda *a, **kw: (0, "applied", "fixture hook warning"))
    agent = Agent(Client(), Runner(policy(), confirm=lambda call: True))
    assert "Stopped" in agent.ask("Re-apply the current theme")
    assert agent.last_status == "error" and len(agent.last_results) == 1


def test_theme_preview_discloses_pipeline_side_effects(theme_repo):
    import io
    from os_assistant.presentation import render_preview
    output = io.StringIO()
    render_preview(policy().prepare("set_theme", {"palette": "nord"}), output)
    assert "app configurations" in output.getvalue() and "restart desktop" in output.getvalue()


@pytest.mark.parametrize("stage", ["before_run", "during_approval"])
def test_pipeline_changes_invalidate_frozen_approval(theme_repo, monkeypatch, stage):
    runner = Runner(policy())
    call = runner.policy.prepare("set_theme", {"palette": "nord"})
    hook = theme_repo / "themes/hooks/fake.sh"
    monkeypatch.setattr(execution.subprocess, "Popen", lambda *a, **kw: pytest.fail("Changed pipeline executed"))
    if stage == "before_run":
        hook.write_text("changed fixture\n")
        runner.confirm = lambda call: pytest.fail("Changed pipeline requested approval")
    else:
        def approve(call):
            hook.write_text("changed fixture\n")
            return True
        runner.confirm = approve
    with pytest.raises(PolicyError, match="changed"):
        runner.run(call)


@pytest.mark.parametrize("relative", ["themes/themectl", "themes/hooks/fake.sh", "plugins/pluginctl"])
def test_untrusted_write_permissions_are_rejected(theme_repo, relative):
    (theme_repo / relative).chmod(0o777)
    with pytest.raises(PolicyError, match="non-writable-by-others"):
        policy().prepare("set_theme", {"palette": "nord"})


def test_helper_symlinks_are_rejected(theme_repo):
    helper = theme_repo / "themes/themectl"
    other = theme_repo / "fixture-helper"
    helper.rename(other)
    helper.symlink_to(other)
    with pytest.raises(PolicyError, match="symlink"):
        themes.catalogue()


def test_runtime_generations_do_not_change_source_snapshot(theme_repo):
    before = themes.snapshot()
    generation = theme_repo / "themes/.generations/new"
    generation.mkdir(parents=True)
    (generation / ".theme-name").write_text("nord\n")
    (theme_repo / "themes/out").symlink_to(generation)
    (theme_repo / "themes/.apply.lock").touch()
    assert themes.snapshot() == before


def test_theme_environment_preserves_only_required_extra_values(monkeypatch):
    for name in ("XDG_STATE_HOME", "HYPRLAND_INSTANCE_SIGNATURE", "AWESOME_THEME",
                 "PRIVATE_API_TOKEN", "LD_PRELOAD", "BASH_ENV", "PYTHONPATH"):
        monkeypatch.setenv(name, "fixture")
    environment = theme_environment()
    assert all(environment[name] == "fixture" for name in ("XDG_STATE_HOME", "HYPRLAND_INSTANCE_SIGNATURE", "AWESOME_THEME"))
    assert not {"PRIVATE_API_TOKEN", "LD_PRELOAD", "BASH_ENV", "PYTHONPATH"} & environment.keys()


def test_capture_separates_output_and_bounds_combined_streams():
    code, stdout, stderr = run_captured((sys.executable, "-I", "-c", "import sys; print('out'); print('warn', file=sys.stderr)"), 2)
    assert code == 0 and stdout == "out\n" and stderr == "warn\n"
    with pytest.raises(AssistantError, match="output limit"):
        run_captured((sys.executable, "-I", "-c", "import sys; sys.stdout.write('x'*5000); sys.stderr.write('y'*5000)"), 2)


def test_strict_theme_configuration_and_defaults(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[themes]\nenabled = true\ntimeout = 90\n")
    config = load_config(path)
    assert config.themes_enabled and config.theme_timeout == 90 and not config.actions_enabled
    assert not Config().themes_enabled


@pytest.mark.parametrize("section", [
    "enabled = 1", "enabled = 'yes'", "timeout = 9", "timeout = 181", "timeout = true",
    "helper = '/bin/sh'", "command = 'set'", "enabled = true\nunknown = 1",
])
def test_invalid_theme_configuration_is_rejected(tmp_path, section):
    from os_assistant.contracts import ConfigurationError
    path = tmp_path / "config.toml"
    path.write_text("[themes]\n" + section + "\n")
    with pytest.raises(ConfigurationError):
        load_config(path)
