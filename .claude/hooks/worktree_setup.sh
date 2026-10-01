#!/usr/bin/env bash
# SessionStart / SubagentStart hook。Claude Code が作った worktree で共通の
# scripts/bootstrap-worktree.sh を実行する（Orca・Codex と同じ setup）。
#
# worktree の作成と削除は Claude Code に任せ、WorktreeCreate hook は使わない。
# hook で作った worktree は、Claude Code が subagent の終了時にも定期の掃除でも削除しない。
#
# すべてのセッションと subagent で走るので、worktree 以外では何もせず、git・sed と bootstrap が使うもの（uv、devenv 経路では direnv と devenv）以外に頼らない。
# Claude Code は hook を作業ディレクトリで実行する（stdin の cwd と同じ）。
#   SessionStart : `claude --worktree` なら新しい worktree
#   SubagentStart: isolation: worktree の subagent なら、その subagent の worktree
# stdout は使わない。SessionStart の stdout は Claude の文脈に入るため、出力は stderr へ。

set -euo pipefail
exec >&2

log() { printf '[worktree-setup] %s\n' "$*"; }

WORKTREE_PATH="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
WORKTREE_PATH="$(cd "$WORKTREE_PATH" && pwd -P)"
MAIN_CHECKOUT="$(git worktree list --porcelain | sed -n '1s/^worktree //p')"
MAIN_CHECKOUT="$(cd "$MAIN_CHECKOUT" && pwd -P)"

# Claude Code の worktree（<main checkout>/.claude/worktrees/<name>）だけを扱う。
# main checkout の .venv は利用者が管理する。セッションのたびに入れ直すと、利用者が選んだ Python や group を上書きしうる。
# Orca と Codex の worktree は、それぞれの setup で準備済み。
case "$WORKTREE_PATH" in
  "$MAIN_CHECKOUT/.claude/worktrees/"*) ;;
  *) exit 0 ;;
esac

# bootstrap を持たないコミット（導入前のコミット）の worktree では何もしない。
BOOTSTRAP="$WORKTREE_PATH/scripts/bootstrap-worktree.sh"
if [ ! -f "$BOOTSTRAP" ]; then
  log "skipping: this commit has no scripts/bootstrap-worktree.sh"
  exit 0
fi

# 準備は worktree ごとに 1 回だけ（作成時）。Orca・Codex と同じで、毎回の起動と subagent の開始は待たせない。
# 完了の印は worktree 専用の git dir に置くので、worktree を消せば一緒に消える。
# 依存を変えたあとは、その worktree で bash scripts/bootstrap-worktree.sh を手で実行する。
DONE_MARK="$(git rev-parse --path-format=absolute --git-path worktree-setup.done)"
if [ -e "$DONE_MARK" ]; then
  exit 0
fi
bash "$BOOTSTRAP" "$WORKTREE_PATH"
: >"$DONE_MARK"
