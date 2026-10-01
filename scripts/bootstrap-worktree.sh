#!/usr/bin/env bash
# 新しい worktree の開発環境を用意する。Orca（orca.yaml）、Codex
# （.codex/environments/environment.toml）、Claude Code の SessionStart / SubagentStart hook
# （.claude/hooks/worktree_setup.sh）の三つがこの一本を呼ぶ。
#
# usage: bootstrap-worktree.sh [WORKTREE_PATH]
#   省略時はカレントディレクトリを含む worktree（Orca と Codex はそこで setup を実行する）。
#
# 何度実行してもよい。poetry install は足りないものだけを入れる。

set -euo pipefail

log() { printf '[bootstrap-worktree] %s\n' "$*" >&2; }
die() {
  log "ERROR: $*"
  exit 1
}

# ---- リポジトリごとの値（ここだけを変える。出どころを各行の上に書く） ----
# devenv.nix の languages.python.version と同じ版（ホスト経路でも揃える）。
PYTHON_VERSION=3.9
# CI（.github/workflows/ci.yml）の POETRY_VERSION と同じ版。
POETRY_VERSION=2.2.1
# CI（.github/workflows/ci.yml）の pytest 用 install と同じ引数。
INSTALL_ARGS=(--no-interaction)
# ---- ここから下は poetry 系のリポジトリで共通 ----

command -v git >/dev/null 2>&1 || die "git is required"

WORKTREE_PATH="$(git -C "${1:-.}" rev-parse --show-toplevel)"
MAIN_CHECKOUT="$(git -C "$WORKTREE_PATH" worktree list --porcelain | sed -n '1s/^worktree //p')"
cd "$WORKTREE_PATH"

# .venv が別の checkout の環境への symlink だと、poetry がその先を書き換える。
[ ! -L .venv ] || die "$WORKTREE_PATH/.venv must not be a symlink"

# .worktreeinclude のファイル（.env など）を main checkout から写す。ツールが写した worktree では
# 既にあるので何もしない。git worktree add で作った worktree のためにある。既にあるものは上書きしない。
# 最後の行に改行が無くても読む（read はその行を返すが偽で終わる）。
if [ -f .worktreeinclude ]; then
  while IFS= read -r path || [ -n "$path" ]; do
    # 前後の空白と CRLF の \r を落とす。残すと、そのパスのファイルは見つからず何も写さない。
    path="${path#"${path%%[![:space:]]*}"}"
    path="${path%"${path##*[![:space:]]}"}"
    case "$path" in "" | "#"*) continue ;; esac
    if [ -e "$path" ] || [ -L "$path" ]; then
      continue
    fi
    if [ ! -f "$MAIN_CHECKOUT/$path" ]; then
      log "not copied: $path is not in $MAIN_CHECKOUT"
      continue
    fi
    mkdir -p "$(dirname "$path")"
    cp "$MAIN_CHECKOUT/$path" "$path"
    log "copied $path from $MAIN_CHECKOUT"
  done <.worktreeinclude
fi

# 仮想環境はこの worktree の .venv に固定する。呼び出し元のシェルから VIRTUAL_ENV を
# 引き継ぐと、poetry はその環境（main checkout の .venv など）に入れてしまう。
export POETRY_VIRTUALENVS_IN_PROJECT=true POETRY_VIRTUALENVS_CREATE=true
unset VIRTUAL_ENV

# devenv.nix のあるリポジトリでは、devenv が用意する Python・Poetry・ネイティブライブラリ
# （mysqlclient のビルドに使う MYSQLCLIENT_CFLAGS など）で入れる。
USE_DIRENV=false
if [ -f devenv.nix ] && [ -f .envrc ] \
  && command -v direnv >/dev/null 2>&1 && command -v devenv >/dev/null 2>&1; then
  if direnv allow >/dev/null 2>&1; then
    USE_DIRENV=true
    log "direnv allowed"
  else
    log "WARN: direnv allow failed; continuing with the host environment"
  fi
elif [ -f devenv.nix ]; then
  log "WARN: devenv needs .envrc, direnv and devenv; continuing with the host environment"
fi

# devenv は入るたびに、全 worktree で共有する hooks（git rev-parse --git-path hooks）へ、その checkout の
# .pre-commit-config.yaml を絶対パスで指す git hook を入れる（上流で追跡中: cachix/devenv#2511）。
# setup で入った worktree が消えると、ほかの checkout の commit が設定を見失うので、setup の前の状態に戻す。
HOOKS_DIR=""
HOOKS_SNAPSHOT=""
restore_hooks() {
  local hook
  [ -n "$HOOKS_SNAPSHOT" ] || return 0
  for hook in "$HOOKS_DIR"/*; do
    [ -e "$hook" ] || [ -L "$hook" ] || continue
    if [ ! -e "$HOOKS_SNAPSHOT/${hook##*/}" ] && [ ! -L "$HOOKS_SNAPSHOT/${hook##*/}" ]; then
      rm -rf "$hook"
    fi
  done
  mkdir -p "$HOOKS_DIR"
  cp -pR "$HOOKS_SNAPSHOT/." "$HOOKS_DIR/"
  rm -rf "$HOOKS_SNAPSHOT"
}
if [ "$USE_DIRENV" = true ]; then
  HOOKS_DIR="$(git rev-parse --path-format=absolute --git-path hooks)"
  HOOKS_SNAPSHOT="$(mktemp -d)"
  if [ -d "$HOOKS_DIR" ]; then
    cp -pR "$HOOKS_DIR/." "$HOOKS_SNAPSHOT/"
  fi
  trap restore_hooks EXIT
fi

PYTHON_MINOR="$(printf '%s' "$PYTHON_VERSION" | cut -d. -f1,2)"
if [ "$USE_DIRENV" = true ]; then
  # direnv exec は .envrc を読むだけで chdir しない（run_poetry が先に worktree へ移る）。
  # devenv は .venv を有効化して VIRTUAL_ENV を設定するため、その内側でもう一度外す。
  POETRY=(direnv exec "$WORKTREE_PATH" env -u VIRTUAL_ENV
    POETRY_VIRTUALENVS_IN_PROJECT=true POETRY_VIRTUALENVS_CREATE=true poetry)
else
  command -v uv >/dev/null 2>&1 || die "uv is required: https://docs.astral.sh/uv/"
  if ! PYTHON="$(uv python find "$PYTHON_VERSION" 2>/dev/null)"; then
    log "installing Python $PYTHON_VERSION"
    uv python install "$PYTHON_VERSION"
    PYTHON="$(uv python find "$PYTHON_VERSION")"
  fi
  # Poetry 自体も同じ Python で動かす。uvx の既定の Python で動かすと、env use に渡した版ではなく
  # Poetry を動かしている版で .venv を作る組み合わせがある（Poetry 2.1.3 で確認）。
  POETRY=(uvx --python "$PYTHON" --from "poetry==$POETRY_VERSION" poetry)
fi

run_poetry() {
  (
    cd "$WORKTREE_PATH"
    "${POETRY[@]}" "$@"
  )
}

# poetry の環境が、この worktree の .venv で、決めた版の Python であることを確かめる。
check_environment() {
  local environment version
  environment="$(run_poetry env info --path)"
  [ "$environment" = "$WORKTREE_PATH/.venv" ] \
    || die "poetry environment is not $WORKTREE_PATH/.venv: ${environment:-none}"
  version="$("$environment/bin/python" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
  [ "$version" = "$PYTHON_MINOR" ] \
    || die "$environment uses Python $version, not $PYTHON_MINOR (remove .venv and run again)"
}

if [ "$USE_DIRENV" = true ]; then
  # devenv の poetry 連携は自分の Python で .venv を作るが、install.enable = false のリポジトリでは作らない。
  # まだ無ければ devenv の Python で作る。PATH の python3 は別の版のことがあるので、版を名指しする。
  if ! run_poetry env info --path >/dev/null; then
    run_poetry env use "python$PYTHON_MINOR"
  fi
else
  run_poetry env use "$PYTHON"
fi

check_environment
log "installing $WORKTREE_PATH/.venv"
run_poetry install "${INSTALL_ARGS[@]}"
check_environment
log "done"
