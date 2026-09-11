{
  pkgs,
  lib,
  config,
  inputs,
  ...
}:

{
  # Python 3.9 + poetry
  languages.python = {
    enable = true;
    version = "3.9";
    poetry.enable = true;
  };

  dotenv.enable = true;

  # mysqlclient のビルドに必要なシステム依存
  packages = [
    # MySQL
    pkgs.libmysqlclient
    pkgs.libmysqlclient.dev
    pkgs.pkg-config
    pkgs.openssl

    # Linter / Formatter
    pkgs.ruff
    pkgs.nixfmt-rfc-style
    pkgs.treefmt

    # LSP / Type Checker
    pkgs.basedpyright

  ];

  # mysqlclient ビルド用の環境変数
  env = {
    MYSQLCLIENT_CFLAGS = "-I${pkgs.libmysqlclient.dev}/include/mariadb";
    MYSQLCLIENT_LDFLAGS = "-L${pkgs.libmysqlclient}/lib/mariadb -lmariadb";
  };

  # git hooks
  git-hooks.hooks = {
    ruff.enable = true;
    ruff-format.enable = true;
    nixfmt-rfc-style.enable = true;
  };

  enterShell = ''
    echo "Python $(python --version | cut -d' ' -f2)"
    echo "poetry $(poetry --version | cut -d' ' -f3)"
    echo "mariadb_config: $(which mariadb_config)"
    echo ""
    echo "Commands:"
    echo "  treefmt               # format all (nix, python)"
    echo "  ruff check .          # lint"
    echo "  ruff format .         # format python"
    echo "  pre-commit run --all  # run all hooks"

    # treefmt / git-hooks は PATH の ruff (nixpkgs 由来)、CI は poetry.lock の版で
    # 判定する。両者がずれると整形結果が食い違うので、入室時に気付けるようにする。
    # direnv はサブディレクトリに cd しただけでも .envrc を再実行するため、cwd では
    # なくリポジトリルートの lock を見る (cwd 相対だと最も普通の経路で黙る)。
    # 恒久的に揃えるなら hooks を .venv/bin/ruff に向ける手もある (#27)。
    repo_root=$(git rev-parse --show-toplevel 2>/dev/null)
    lock_file="$repo_root/poetry.lock"
    if [ -n "$repo_root" ] && [ -f "$lock_file" ]; then
      lock_ruff=$(grep -A1 '^name = "ruff"$' "$lock_file" | sed -n 's/^version = "\(.*\)"$/\1/p')
      path_ruff=$(ruff --version 2>/dev/null | cut -d' ' -f2)
      if [ -n "$lock_ruff" ] && [ -n "$path_ruff" ] && [ "$lock_ruff" != "$path_ruff" ]; then
        echo ""
        echo "WARNING: ruff mismatch - PATH $path_ruff / poetry.lock $lock_ruff"
        echo "  CI is judged by the poetry.lock version. See issue #27."
      fi
    fi
  '';
}
