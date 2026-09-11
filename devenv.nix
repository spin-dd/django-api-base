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

    # git-hooks の ruff だけは nixpkgs の store path を直接叩く
    # (git-hooks.nix: entry = "''${hooks.ruff.package}/bin/ruff check --fix")。
    # treefmt (command = "ruff") と手打ちの ruff は PATH 解決で、poetry が
    # enterShell より前に activate する .venv/bin/ruff = poetry.lock の版が当たる。
    # CI も lock の版。つまりずれるのは git-hooks とそれ以外の間なので、
    # nixpkgs 側と lock を突き合わせる。PATH の ruff と比べても lock 同士の比較に
    # なって永久に発火しない。
    # direnv はサブディレクトリに cd しただけでも .envrc を再実行するため、cwd では
    # なくプロジェクトルートの lock を見る (cwd 相対だと最も普通の経路で黙る)。
    # git は使わない。このシェルの /usr/bin/git は xcrun のシムで、実機では
    # "error: tool 'git' not found" になり、ガードが黙ってスキップされる。
    lock_file="''${DEVENV_ROOT:-.}/poetry.lock"
    [ -f "$lock_file" ] || lock_file=poetry.lock
    if [ -f "$lock_file" ]; then
      lock_ruff=$(grep -A1 '^name = "ruff"$' "$lock_file" | sed -n 's/^version = "\(.*\)"$/\1/p')
      nix_ruff=$(${pkgs.ruff}/bin/ruff --version 2>/dev/null | cut -d' ' -f2)
      if [ -n "$lock_ruff" ] && [ -n "$nix_ruff" ] && [ "$lock_ruff" != "$nix_ruff" ]; then
        echo ""
        echo "WARNING: ruff mismatch - git-hooks (nixpkgs) $nix_ruff / poetry.lock $lock_ruff"
        echo "  treefmt and CI use the poetry.lock version. See issue #27."
      fi
    fi
  '';
}
