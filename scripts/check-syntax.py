#!/usr/bin/env python3
"""Read-only lint/syntax checks for first-party code, including new Git inputs."""
import ast
from pathlib import Path
import shutil
import subprocess
import sys
from config_syntax import ConfigSyntaxError, validate_file


ROOT = Path(__file__).resolve().parents[1]
VENDORED = (
    "awesome/.config/awesome/awesome-buttons/",
    "awesome/.config/awesome/awesome-wm-widgets/",
    "awesome/.config/awesome/freedesktop/",
    "awesome/.config/awesome/lain/",
    "awesome/.config/awesome/volume-widget/",
    "zsh/.config/zsh/zsh-autocomplete/",
    "scripts/.local/lib/python",
    "scripts/.local/bin/git-filter-repo",
)
# Inner suffix -> shell dialect for templates such as env.sh.tpl.
TEMPLATE_DIALECTS = {".sh": "sh", ".bash": "bash", ".zsh": "zsh"}


def main():
    required = ("bash", "sh", "zsh", "shellcheck", "luac")
    missing = [tool for tool in required if not shutil.which(tool)]
    if missing:
        print("Missing check tools: " + ", ".join(missing), file=sys.stderr)
        return 1
    names = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT,
    ).decode().split("\0")
    counts = {"shell": 0, "zsh": 0, "lua": 0, "python": 0,
              "json": 0, "jsonc": 0, "toml": 0, "yaml": 0}
    shell_files = {"bash": [], "sh": []}
    failed = False
    for name in sorted(set(filter(None, names))):
        path = ROOT / name
        if name.startswith(VENDORED) or path.is_symlink() or not path.is_file():
            continue
        with path.open("rb") as stream:
            head = stream.read(4096).decode(errors="replace").splitlines()
        first = head[0].strip() if head else ""
        command = None
        suffix = path.suffix.lower()
        config_format = {".json": "json", ".jsonc": "jsonc", ".toml": "toml",
                         ".yaml": "yaml", ".yml": "yaml"}.get(suffix)
        if config_format:
            counts[config_format] += 1
            fragment = (path.name == "waybar-defs.jsonc" and
                        len(path.relative_to(ROOT).parts) == 3 and
                        path.relative_to(ROOT).parts[0] == "plugins")
            try:
                validate_file(path, format=config_format, fragment=fragment)
            except ConfigSyntaxError as error:
                print(error, file=sys.stderr)
                failed = True
        elif path.suffix == ".py" or (first.startswith("#!") and "python" in first):
            counts["python"] += 1
            try:
                ast.parse(path.read_text(), filename=name)
            except (SyntaxError, UnicodeError) as error:
                print(error, file=sys.stderr)
                failed = True
        elif path.suffix == ".lua":
            counts["lua"] += 1
            command = ["luac", "-p", name]
        elif path.suffix == ".tpl":
            # Shell templates declare their dialect in a shebang (possibly after
            # template header comments) or in the suffix before .tpl (env.sh.tpl).
            shebang = next((line.strip() for line in head[:8] if line.strip().startswith("#!")), "")
            dialect = ("zsh" if "zsh" in shebang
                       else "sh" if shebang.endswith(("/sh", " sh"))
                       else "bash" if "bash" in shebang
                       else TEMPLATE_DIALECTS.get(Path(path.stem).suffix))
            if dialect:
                counts["zsh" if dialect == "zsh" else "shell"] += 1
                # Syntax-check only: {{...}} template values make shellcheck
                # unreliable (e.g. SC2034 on variables consumed when sourced).
                command = [dialect, "-n", name]
        elif ((first.startswith("#!") and "zsh" in first) or path.suffix == ".zsh"
              or (path.parent.name == "completions" and path.name.startswith("_"))):
            counts["zsh"] += 1
            command = ["zsh", "-n", name]
        elif first.startswith("#!") and (first.endswith("/sh") or first.endswith(" sh")):
            counts["shell"] += 1
            shell_files["sh"].append(name)
            command = ["sh", "-n", name]
        elif ((first.startswith("#!") and "bash" in first) or path.suffix in (".sh", ".bash")
              or name in ("bash/.bashrc", "bash/.config/bash/bashrc")):
            counts["shell"] += 1
            shell_files["bash"].append(name)
            command = ["bash", "-n", name]
        if command and subprocess.run(command, cwd=ROOT).returncode:
            failed = True
    for dialect, files in shell_files.items():
        if files and subprocess.run(["shellcheck", "--shell=" + dialect, *files], cwd=ROOT).returncode:
            failed = True
    print("Checked " + ", ".join(f"{count} {kind}" for kind, count in counts.items()))
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
