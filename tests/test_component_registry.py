"""Component metadata and CLI behavior share the registry."""

import subprocess
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def bash(script, *args):
    with tempfile.TemporaryDirectory(prefix="component-registry-") as temp:
        fixture = Path(temp)
        lib = fixture / "lib"
        lib.mkdir()
        for filename in ("component-registry.sh", "logging.sh", "args.sh"):
            shutil.copyfile(ROOT / "lib" / filename, lib / filename)
        home = fixture / "home"
        home.mkdir()
        path = fixture / "bin"
        path.mkdir()
        for name in ("bash", "basename", "dirname", "sort", "wc"):
            executable = shutil.which(name)
            if executable:
                (path / name).symlink_to(executable)
        env = {
            "HOME": str(home), "PATH": str(path), "TMPDIR": str(fixture),
            "LC_ALL": "C", "TERM": "dumb",
        }
        return subprocess.run(
            [shutil.which("bash"), "--noprofile", "--norc", "-c",
             "set -euo pipefail\n" + script, "test", *args],
            cwd=fixture, env=env, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, check=False, timeout=5,
        )


def test_registry_steps_unique_and_execution_order_complete():
    result = bash(r'''
source lib/component-registry.sh
names=() steps=()
for item in "${COMPONENTS[@]}"; do
    names+=("$(get_component_name "$item")")
    steps+=("$(get_component_step "$item")")
done
[[ $(printf '%s\n' "${names[@]}" | sort -u | wc -l) -eq ${#names[@]} ]]
[[ $(printf '%s\n' "${steps[@]}" | sort -u | wc -l) -eq ${#steps[@]} ]]
[[ ${#INSTALL_STEP_ORDER[@]} -eq ${#steps[@]} ]]
expected=(yay packages node yubikey stow theme backgrounds tmux shell lazyvim)
[[ "${INSTALL_STEP_ORDER[*]}" == "${expected[*]}" ]]
for step in "${steps[@]}"; do
    [[ " ${INSTALL_STEP_ORDER[*]} " == *" $step "* ]]
done
for step in "${INSTALL_STEP_ORDER[@]}"; do component_step_known "$step"; done
''')
    assert result.returncode == 0, result.stdout


def test_help_names_and_descriptions_come_from_registry():
    result = bash(r'''
source lib/logging.sh
source lib/args.sh
show_help
''')
    assert result.returncode == 0, result.stdout
    for step, desc in (
        ("yay", "AUR helper (yay)"), ("packages", "System packages"),
        ("shell", "Default shell (zsh or bash; requires stow)"),
        ("theme", "Desktop color palette"), ("yubikey", "YubiKey tools (optional)"),
    ):
        assert step in result.stdout
        assert desc in result.stdout
    assert "Alacritty" not in result.stdout
    metadata = bash(r'''
source lib/component-registry.sh
for component in "${COMPONENTS[@]}"; do
    printf '%s|%s\n' "$(get_component_step "$component")" "$(get_component_desc "$component")"
done
''')
    assert metadata.returncode == 0, metadata.stdout
    for line in metadata.stdout.splitlines():
        step, description = line.split("|", 1)
        assert step in result.stdout
        assert description in result.stdout


def test_appended_registry_step_is_valid_and_shown_without_dispatch():
    result = bash(r'''
source lib/logging.sh
source lib/args.sh
COMPONENTS+=("synthetic|Synthetic fixture|false|synthetic")
INSTALL_STEP_ORDER+=(synthetic)
parse_args --only synthetic
[[ "${RUN_STEPS[*]}" == synthetic ]]
show_help
''')
    assert result.returncode == 0, result.stdout
    assert "synthetic" in result.stdout
    assert "Synthetic fixture" in result.stdout


def test_repeated_sourcing_does_not_reset_metadata_or_cli_flags():
    result = bash(r'''
source lib/args.sh
parse_args --only packages --skip theme
source lib/component-registry.sh
source lib/args.sh
[[ "${RUN_STEPS[*]}" == packages ]]
[[ "${SKIP_STEPS[*]}" == theme ]]
[[ ${#COMPONENTS[@]} -eq 10 ]]
''')
    assert result.returncode == 0, result.stdout
