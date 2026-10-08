"""Worktree setup shared by Orca, Codex and Claude Code.

The scripts run against a scratch Git repository. External tools are replaced
by stubs that record their arguments, directory and environment.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_FILES = (
    "scripts/bootstrap-worktree.sh",
    ".claude/hooks/worktree_setup.sh",
    ".claude/settings.json",
    ".codex/environments/environment.toml",
    "orca.yaml",
)
TOOL_STUB = """#!/bin/sh
tool="${0##*/}"
printf '%s\\t%s\\t%s\\t%s\\t%s\\t%s\\n' "$tool" "$(pwd -P)" "${VIRTUAL_ENV-}" \
  "${POETRY_VIRTUALENVS_IN_PROJECT-}" "${POETRY_VIRTUALENVS_CREATE-}" "$*" >> "$TOOL_STUB_LOG"
if [ "$tool" = direnv ]; then
  if [ "$1" = allow ] && [ -n "${TOOL_STUB_DIRENV_ALLOW_FAIL-}" ]; then exit 7; fi
  if [ "$1" = exec ]; then
    if [ -n "${TOOL_STUB_MUTATE_HOOKS-}" ]; then
      hooks="$(git rev-parse --path-format=absolute --git-path hooks)"
      printf '#!/bin/sh\\n# installed by devenv\\n' > "$hooks/pre-commit"
      chmod 600 "$hooks/pre-commit"
      printf '#!/bin/sh\\n# new devenv hook\\n' > "$hooks/prepare-commit-msg"
    fi
    shift 2
    export VIRTUAL_ENV="$PWD/.venv"
    export POETRY_VIRTUALENVS_IN_PROJECT=false POETRY_VIRTUALENVS_CREATE=false
    exec "$@"
  fi
  exit 0
elif [ "$tool" = mktemp ]; then
  exec "$TOOL_STUB_REAL_MKTEMP" "$@"
elif [ "$tool" = uv ]; then
  if [ "$*" = 'python find 3.9' ] && [ -n "${TOOL_STUB_PYTHON_MISSING-}" ] \
    && [ ! -e "$TOOL_STUB_LOG.python-installed" ]; then exit 1; fi
  if [ "$*" = 'python install 3.9' ]; then : > "$TOOL_STUB_LOG.python-installed"; fi
  printf '/stub/python3.9\\n'
else
  if [ "$tool" = uvx ]; then shift 5; fi
  if [ "$*" = 'env info --path' ]; then
    if [ -n "${TOOL_STUB_NO_VENV-}" ] && [ ! -e .stub-env-created ]; then exit 1; fi
    if [ -n "${TOOL_STUB_ENV_PATH_AFTER-}" ] && [ -e .stub-installed ]; then
      printf '%s\\n' "$TOOL_STUB_ENV_PATH_AFTER"
      exit 0
    fi
    mkdir -p .venv/bin
    cp "$TOOL_STUB_VENV_PYTHON" .venv/bin/python
    printf '%s\\n' "${TOOL_STUB_ENV_PATH:-$PWD/.venv}"
    exit 0
  fi
  if [ -n "${TOOL_STUB_FAIL-}" ] && [ "$*" = 'install --no-interaction' ]; then exit 7; fi
  if [ "$1" = env ] && [ "$2" = use ]; then : > .stub-env-created; fi
  if [ "$*" = 'install --no-interaction' ]; then : > .stub-installed; fi
  echo "$tool $*"
fi
"""
HARNESS_ENV = (
    "ORCA_ROOT_PATH",
    "ORCA_WORKTREE_PATH",
    "CODEX_SOURCE_TREE_PATH",
    "CODEX_WORKTREE_PATH",
    "CLAUDE_PROJECT_DIR",
    "VIRTUAL_ENV",
    "POETRY_VIRTUALENVS_IN_PROJECT",
    "POETRY_VIRTUALENVS_CREATE",
)


class Project:
    """A scratch repository holding copies of this project's worktree scripts."""

    def __init__(self, root: Path, env: dict[str, str], tool_log: Path):
        self.root = root
        self.env = env
        self.tool_log = tool_log

    def run(self, *args, cwd, env=None, stdin=None):
        return subprocess.run(
            args,
            cwd=cwd,
            env={**self.env, **(env or {})},
            input=stdin,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def git(self, *args, cwd=None):
        result = self.run("git", *args, cwd=cwd or self.root)
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    def tool_calls(self, tool):
        if not self.tool_log.exists():
            return []
        return [
            tuple(line.split("\t")[1:])
            for line in self.tool_log.read_text().splitlines()
            if line.split("\t")[0] == tool
        ]

    def worktree(self, name="app-worktree"):
        worktree = self.root.parent / name
        self.git("worktree", "add", "-q", "-b", name, str(worktree))
        return worktree.resolve()


def git_binary() -> Path:
    """Resolve Git's real executable using the unrestricted host PATH.

    On macOS, symlinking the /usr/bin/git shim into a restricted PATH can make
    xcrun repeatedly invoke the same shim. The executable in --exec-path avoids this.
    """
    exec_path = subprocess.run(
        ["git", "--exec-path"], capture_output=True, text=True, check=True, timeout=30
    ).stdout.strip()
    binary = Path(exec_path) / "git"
    assert os.access(binary, os.X_OK), binary
    return binary


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    for relative in PROJECT_FILES:
        source = PROJECT_ROOT / relative
        if source.exists():
            (root / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, root / relative)
    (root / ".gitignore").write_text(".claude/worktrees/\n.venv/\n.stub-installed\n.stub-env-created\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in ("bash", "git", "sed", "env", "cut", "mkdir", "cp", "rm", "chmod"):
        path = git_binary() if tool == "git" else shutil.which(tool)
        (bin_dir / tool).symlink_to(path)
    for tool in ("uv", "uvx", "poetry", "direnv", "devenv", "mktemp"):
        (bin_dir / tool).write_text(TOOL_STUB)
        (bin_dir / tool).chmod(0o755)
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in HARNESS_ENV and not key.startswith("GIT_") and not key.startswith("TOOL_STUB_")
    }
    venv_python = bin_dir / "venv-python"
    venv_python.write_text(
        "#!/bin/sh\n"
        'if [ -n "${TOOL_STUB_PYTHON_MINOR_AFTER-}" ] && [ -e .stub-installed ]; then\n'
        "  printf '%s\\n' \"$TOOL_STUB_PYTHON_MINOR_AFTER\"\n"
        "else\n  printf '%s\\n' \"${TOOL_STUB_PYTHON_MINOR:-3.9}\"\nfi\n"
    )
    venv_python.chmod(0o755)
    env.update(
        PATH=str(bin_dir),
        TOOL_STUB_LOG=str(tmp_path / "tools.log"),
        TOOL_STUB_VENV_PYTHON=str(venv_python),
        TOOL_STUB_REAL_MKTEMP=shutil.which("mktemp"),
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_AUTHOR_NAME="test",
        GIT_AUTHOR_EMAIL="test@example.com",
        GIT_COMMITTER_NAME="test",
        GIT_COMMITTER_EMAIL="test@example.com",
    )
    project = Project(root.resolve(), env, tmp_path / "tools.log")
    for relative in ("devenv.nix", ".envrc"):
        (root / relative).write_text("# devenv config\n")
    project.git("init", "-q", "-b", "main")
    project.git("add", ".gitignore", "devenv.nix", ".envrc", *[p for p in PROJECT_FILES if (root / p).exists()])
    project.git("commit", "-q", "-m", "init")
    return project


def test_bootstrap_installs_into_the_worktrees_devenv_environment(project):
    worktree = project.worktree()
    result = project.run(
        "bash",
        "scripts/bootstrap-worktree.sh",
        cwd=worktree,
        env={
            "VIRTUAL_ENV": str(project.root / ".venv"),
            "POETRY_VIRTUALENVS_IN_PROJECT": "false",
            "POETRY_VIRTUALENVS_CREATE": "false",
        },
    )
    assert result.returncode == 0, result.stderr
    calls = project.tool_calls("poetry")
    assert all(call[:4] == (str(worktree), "", "true", "true") for call in calls)
    assert [call[-1] for call in calls] == [
        "env info --path",
        "env info --path",
        "install --no-interaction",
        "env info --path",
    ]
    assert [call[-1] for call in project.tool_calls("direnv")][0] == "allow"
    assert all(call[-1].startswith(f"exec {worktree} ") for call in project.tool_calls("direnv")[1:])
    assert project.tool_calls("uv") == project.tool_calls("uvx") == []


def add_claude_worktree(project, name):
    worktree = project.root / ".claude/worktrees" / name
    project.git("worktree", "add", "-q", "-b", f"worktree-{name}", str(worktree))
    return worktree


def run_setup_hook(project, event, cwd, project_dir=None, env=None):
    """Run SessionStart / SubagentStart as Claude Code does, including stdin."""
    project_dir = project_dir or project.root
    return project.run(
        "bash",
        str(project_dir / ".claude/hooks/worktree_setup.sh"),
        cwd=cwd,
        stdin=json.dumps({"hook_event_name": event, "cwd": str(cwd)}),
        env={"CLAUDE_PROJECT_DIR": str(project_dir), **(env or {})},
    )


def installs(project, tool="poetry"):
    return [call for call in project.tool_calls(tool) if "install --no-interaction" in call[-1]]


def test_subagent_worktree_is_bootstrapped_before_the_subagent_starts(project):
    worktree = add_claude_worktree(project, "agent-a1")
    result = run_setup_hook(project, "SubagentStart", cwd=worktree)

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert [call[0] for call in installs(project)] == [str(worktree)]


def orca_setup_command(project):
    match = re.search(r"^scripts:\n  setup: (.+)$", (project.root / "orca.yaml").read_text(), re.MULTILINE)
    assert match, "orca.yaml needs a one-line scripts.setup"
    return match.group(1)


def test_orca_setup_runs_the_shared_bootstrap_and_waits_for_setup(project):
    worktree = project.worktree()
    command = orca_setup_command(project)
    assert command == "bash scripts/bootstrap-worktree.sh"
    assert "setupAgentStartupPolicy: wait-for-setup" in (project.root / "orca.yaml").read_text()

    result = project.run(
        "/bin/bash",
        "-e",
        "-c",
        command,
        cwd=worktree,
        env={"ORCA_ROOT_PATH": str(project.root), "ORCA_WORKTREE_PATH": str(worktree)},
    )

    assert result.returncode == 0, result.stderr
    assert [call[0] for call in installs(project)] == [str(worktree)]


def codex_setup_command(project):
    config = (project.root / ".codex/environments/environment.toml").read_text()
    assert re.search(r"^version = 1$", config, re.MULTILINE)
    assert 'name = "Taihei Django API Base"' in config
    match = re.search(r'^\[setup\]\nscript = "([^"]+)"$', config, re.MULTILINE)
    assert match, "environment.toml needs a setup script"
    return match.group(1)


def test_codex_setup_runs_the_shared_bootstrap(project):
    worktree = project.worktree()
    command = codex_setup_command(project)
    assert command == "bash scripts/bootstrap-worktree.sh"

    result = project.run(
        "bash",
        "-e",
        "-c",
        command,
        cwd=worktree,
        env={"CODEX_SOURCE_TREE_PATH": str(project.root), "CODEX_WORKTREE_PATH": str(worktree)},
    )

    assert result.returncode == 0, result.stderr
    assert [call[0] for call in installs(project)] == [str(worktree)]


def test_claude_settings_set_up_new_worktrees(project):
    settings = json.loads((project.root / ".claude/settings.json").read_text())
    assert "worktree" not in settings
    assert "WorktreeCreate" not in settings["hooks"]

    worktrees = []
    for event in ("SessionStart", "SubagentStart"):
        worktree = add_claude_worktree(project, f"wired-{event.lower()}")
        worktrees.append(worktree)
        [matcher] = settings["hooks"][event]
        if event == "SessionStart":
            assert matcher["matcher"] == "startup|resume"
        [hook] = matcher["hooks"]
        assert hook["type"] == "command"
        assert hook["command"] == '"$CLAUDE_PROJECT_DIR"/.claude/hooks/worktree_setup.sh'
        result = project.run(
            "bash",
            "-c",
            hook["command"],
            cwd=worktree,
            stdin=json.dumps({"hook_event_name": event, "source": "startup", "cwd": str(worktree)}),
            env={"CLAUDE_PROJECT_DIR": str(project.root)},
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout == ""

    assert [call[0] for call in installs(project)] == [str(w) for w in worktrees]


def minimal_path(project, tmp_path, excluded=()):
    bin_dir = tmp_path / "minimal-bin"
    bin_dir.mkdir()
    for tool in (
        "bash",
        "git",
        "sed",
        "env",
        "cut",
        "mkdir",
        "cp",
        "rm",
        "mktemp",
        "chmod",
        "uv",
        "uvx",
        "poetry",
        "direnv",
        "devenv",
    ):
        if tool in excluded:
            continue
        path = git_binary() if tool == "git" else shutil.which(tool, path=project.env["PATH"])
        assert path, tool
        (bin_dir / tool).symlink_to(path)
    return str(bin_dir)


def test_host_fallback_uses_the_same_python_and_ci_poetry(project, tmp_path):
    worktree = project.worktree()
    result = project.run(
        "bash",
        "scripts/bootstrap-worktree.sh",
        cwd=worktree,
        env={
            "PATH": minimal_path(project, tmp_path, excluded=("direnv",)),
            "VIRTUAL_ENV": str(project.root / ".venv"),
            "POETRY_VIRTUALENVS_IN_PROJECT": "false",
            "POETRY_VIRTUALENVS_CREATE": "false",
        },
    )
    assert result.returncode == 0, result.stderr
    assert len([line for line in result.stderr.splitlines() if "WARN:" in line]) == 1
    assert [call[-1] for call in project.tool_calls("uv")] == ["python find 3.9"]
    calls = project.tool_calls("uvx")
    assert all(call[:4] == (str(worktree), "", "true", "true") for call in calls)
    assert [call[-1] for call in calls] == [
        "--python /stub/python3.9 --from poetry==2.2.1 poetry env use /stub/python3.9",
        "--python /stub/python3.9 --from poetry==2.2.1 poetry env info --path",
        "--python /stub/python3.9 --from poetry==2.2.1 poetry install --no-interaction",
        "--python /stub/python3.9 --from poetry==2.2.1 poetry env info --path",
    ]
    assert project.tool_calls("poetry") == project.tool_calls("direnv") == []


def test_bootstrap_installs_python_when_the_requested_version_is_missing(project, tmp_path):
    worktree = project.worktree()
    result = project.run(
        "bash",
        "scripts/bootstrap-worktree.sh",
        cwd=worktree,
        env={"TOOL_STUB_PYTHON_MISSING": "1", "PATH": minimal_path(project, tmp_path, excluded=("direnv",))},
    )

    assert result.returncode == 0, result.stderr
    assert [call[-1] for call in project.tool_calls("uv")] == [
        "python find 3.9",
        "python install 3.9",
        "python find 3.9",
    ]


@pytest.mark.parametrize("route", ["devenv", "host"])
@pytest.mark.parametrize("phase", ["before", "after"])
def test_bootstrap_rejects_external_environments_in_both_routes(project, tmp_path, route, phase):
    worktree = project.worktree()
    variable = "TOOL_STUB_ENV_PATH" if phase == "before" else "TOOL_STUB_ENV_PATH_AFTER"
    env = {variable: str(project.root / ".venv")}
    if route == "host":
        env["PATH"] = minimal_path(project, tmp_path, excluded=("direnv",))
    result = project.run("bash", "scripts/bootstrap-worktree.sh", cwd=worktree, env=env)
    assert result.returncode != 0
    assert "ERROR: poetry environment is not" in result.stderr
    assert len(installs(project, "poetry" if route == "devenv" else "uvx")) == (phase == "after")


@pytest.mark.parametrize("route", ["devenv", "host"])
def test_bootstrap_propagates_install_failure_in_both_routes(project, tmp_path, route):
    worktree = project.worktree()
    env = {"TOOL_STUB_FAIL": "1"}
    if route == "host":
        env["PATH"] = minimal_path(project, tmp_path, excluded=("direnv",))
    result = project.run("bash", "scripts/bootstrap-worktree.sh", cwd=worktree, env=env)
    assert result.returncode == 7
    assert "[bootstrap-worktree] done" not in result.stderr


def test_bootstrap_called_from_main_uses_the_explicit_worktree(project):
    worktree = project.worktree()
    result = project.run("bash", str(project.root / "scripts/bootstrap-worktree.sh"), str(worktree), cwd=project.root)
    assert result.returncode == 0, result.stderr
    assert all(call[0] == str(worktree) for call in project.tool_calls("direnv") + project.tool_calls("poetry"))
    assert len(installs(project)) == 1


def test_bootstrap_rejects_a_venv_symlink_before_poetry_can_modify_its_target(project):
    worktree = project.worktree()
    main_venv = project.root / ".venv"
    main_venv.mkdir()
    (worktree / ".venv").symlink_to(main_venv, target_is_directory=True)

    result = project.run("bash", "scripts/bootstrap-worktree.sh", cwd=worktree)

    assert result.returncode != 0
    assert "ERROR:" in result.stderr
    assert project.tool_calls("poetry") == []


def test_session_in_the_main_checkout_leaves_its_environment_alone(project):
    result = run_setup_hook(project, "SessionStart", cwd=project.root)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert project.tool_calls("poetry") == []


def test_worktrees_outside_claude_worktrees_are_left_to_their_own_setup(project):
    worktree = project.worktree()
    result = run_setup_hook(project, "SessionStart", cwd=worktree, project_dir=worktree)
    assert result.returncode == 0, result.stderr
    assert project.tool_calls("poetry") == []


def test_worktree_on_a_commit_without_the_bootstrap_is_skipped(project):
    project.git("switch", "-q", "--orphan", "before-bootstrap")
    project.git("commit", "-q", "--allow-empty", "-m", "before the bootstrap")
    project.git("switch", "-q", "main")
    worktree = project.root / ".claude/worktrees/agent-old"
    project.git("worktree", "add", "-q", str(worktree), "before-bootstrap")
    result = run_setup_hook(project, "SubagentStart", cwd=worktree)
    assert result.returncode == 0, result.stderr
    assert "bootstrap-worktree.sh" in result.stderr
    assert project.tool_calls("poetry") == []


def test_worktree_is_set_up_only_once(project):
    worktree = add_claude_worktree(project, "once")
    mark = Path(project.git("rev-parse", "--path-format=absolute", "--git-path", "worktree-setup.done", cwd=worktree))
    for event in ("SessionStart", "SessionStart", "SubagentStart"):
        result = run_setup_hook(project, event, cwd=worktree, project_dir=worktree)
        assert result.returncode == 0, result.stderr
        assert result.stdout == ""
    assert mark.exists()
    assert [call[0] for call in installs(project)] == [str(worktree)]


def test_failed_setup_is_retried_by_the_next_session(project):
    worktree = add_claude_worktree(project, "retry")
    mark = Path(project.git("rev-parse", "--path-format=absolute", "--git-path", "worktree-setup.done", cwd=worktree))
    failed = run_setup_hook(project, "SessionStart", cwd=worktree, project_dir=worktree, env={"TOOL_STUB_FAIL": "1"})
    assert failed.returncode != 0
    assert not mark.exists()
    retried = run_setup_hook(project, "SessionStart", cwd=worktree, project_dir=worktree)
    assert retried.returncode == 0, retried.stderr
    assert mark.exists()
    assert len(installs(project)) == 2


@pytest.mark.parametrize("missing", ["direnv", "devenv", ".envrc"])
def test_incomplete_devenv_warns_once_and_uses_the_host(project, tmp_path, missing):
    if missing == ".envrc":
        project.git("rm", ".envrc")
        project.git("commit", "-q", "-m", "without envrc")
    worktree = project.worktree()
    result = project.run(
        "bash",
        "scripts/bootstrap-worktree.sh",
        cwd=worktree,
        env={"PATH": minimal_path(project, tmp_path, excluded=(missing,))},
    )
    assert result.returncode == 0, result.stderr
    assert len([line for line in result.stderr.splitlines() if "WARN:" in line]) == 1
    assert project.tool_calls("direnv") == project.tool_calls("poetry") == []
    assert len(installs(project, "uvx")) == 1


def test_failed_direnv_allow_warns_once_and_uses_the_host(project):
    worktree = project.worktree()
    result = project.run(
        "bash",
        "scripts/bootstrap-worktree.sh",
        cwd=worktree,
        env={"TOOL_STUB_DIRENV_ALLOW_FAIL": "1"},
    )

    assert result.returncode == 0, result.stderr
    assert len([line for line in result.stderr.splitlines() if "WARN:" in line]) == 1
    assert [call[-1] for call in project.tool_calls("direnv")] == ["allow"]
    assert project.tool_calls("poetry") == []
    assert len(installs(project, "uvx")) == 1


def test_worktree_session_started_in_a_subdirectory_bootstraps_the_whole_worktree(project):
    (project.root / "tests").mkdir()
    (project.root / "tests/.keep").write_text("")
    project.git("add", "tests/.keep")
    project.git("commit", "-q", "-m", "tests directory")
    worktree = add_claude_worktree(project, "nested-start")
    result = run_setup_hook(project, "SessionStart", cwd=worktree / "tests", project_dir=worktree)
    assert result.returncode == 0, result.stderr
    assert [call[0] for call in installs(project)] == [str(worktree)]


def test_each_worktree_is_set_up_on_its_own(project):
    worktrees = [add_claude_worktree(project, "first"), add_claude_worktree(project, "second")]
    for worktree in worktrees:
        result = run_setup_hook(project, "SubagentStart", cwd=worktree)
        assert result.returncode == 0, result.stderr
    assert [call[0] for call in installs(project)] == [str(w) for w in worktrees]


def test_devenv_creates_a_missing_environment_with_its_own_python(project):
    worktree = project.worktree()
    result = project.run("bash", "scripts/bootstrap-worktree.sh", cwd=worktree, env={"TOOL_STUB_NO_VENV": "1"})
    assert result.returncode == 0, result.stderr
    assert [call[-1] for call in project.tool_calls("poetry")] == [
        "env info --path",
        "env use python3.9",
        "env info --path",
        "install --no-interaction",
        "env info --path",
    ]
    assert project.tool_calls("uv") == project.tool_calls("uvx") == []


def hooks_snapshot(project):
    directory = Path(project.git("rev-parse", "--path-format=absolute", "--git-path", "hooks"))
    return {
        str(path.relative_to(directory)): (path.read_bytes(), path.stat().st_mode, path.stat().st_mtime_ns)
        for path in directory.rglob("*")
        if path.is_file()
    }


def test_devenv_restores_existing_hooks_and_removes_added_hooks(project):
    worktree = project.worktree()
    hooks = Path(project.git("rev-parse", "--path-format=absolute", "--git-path", "hooks"))
    original = hooks / "pre-commit"
    original.write_text("#!/bin/sh\n# original hook\nexit 0\n")
    original.chmod(0o755)
    before = hooks_snapshot(project)

    result = project.run("bash", "scripts/bootstrap-worktree.sh", cwd=worktree, env={"TOOL_STUB_MUTATE_HOOKS": "1"})

    assert result.returncode == 0, result.stderr
    assert hooks_snapshot(project) == before


def test_devenv_restores_hooks_even_when_install_fails(project):
    worktree = project.worktree()
    hooks = Path(project.git("rev-parse", "--path-format=absolute", "--git-path", "hooks"))
    (hooks / "pre-commit").write_text("#!/bin/sh\n# original hook\nexit 0\n")
    before = hooks_snapshot(project)
    result = project.run(
        "bash",
        "scripts/bootstrap-worktree.sh",
        cwd=worktree,
        env={"TOOL_STUB_MUTATE_HOOKS": "1", "TOOL_STUB_FAIL": "1"},
    )
    assert result.returncode == 7, result.stderr
    assert hooks_snapshot(project) == before


def test_host_setup_leaves_shared_hooks_alone(project, tmp_path):
    worktree = project.worktree()
    hooks = Path(project.git("rev-parse", "--path-format=absolute", "--git-path", "hooks"))
    (hooks / "pre-commit").write_text("#!/bin/sh\n# main checkout hook\nexit 0\n")
    before = hooks_snapshot(project)
    result = project.run(
        "bash",
        "scripts/bootstrap-worktree.sh",
        cwd=worktree,
        env={"PATH": minimal_path(project, tmp_path, excluded=("direnv",)), "TOOL_STUB_MUTATE_HOOKS": "1"},
    )
    assert result.returncode == 0, result.stderr
    assert hooks_snapshot(project) == before
    assert project.tool_calls("mktemp") == []
    assert project.tool_calls("direnv") == []


@pytest.mark.parametrize("route", ["devenv", "host"])
@pytest.mark.parametrize("phase", ["before", "after"])
def test_bootstrap_rejects_the_wrong_python_version_before_and_after_install(project, tmp_path, route, phase):
    worktree = project.worktree()
    variable = "TOOL_STUB_PYTHON_MINOR" if phase == "before" else "TOOL_STUB_PYTHON_MINOR_AFTER"
    env = {variable: "3.10"}
    if route == "host":
        env["PATH"] = minimal_path(project, tmp_path, excluded=("direnv",))
    result = project.run("bash", "scripts/bootstrap-worktree.sh", cwd=worktree, env=env)
    assert result.returncode != 0
    assert f"{worktree}/.venv uses Python 3.10, not 3.9" in result.stderr
    assert len(installs(project, "poetry" if route == "devenv" else "uvx")) == (phase == "after")
