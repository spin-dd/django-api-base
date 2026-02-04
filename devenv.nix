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
  ];

  # mysqlclient ビルド用の環境変数
  env = {
    MYSQLCLIENT_CFLAGS = "-I${pkgs.libmysqlclient.dev}/include/mariadb";
    MYSQLCLIENT_LDFLAGS = "-L${pkgs.libmysqlclient}/lib/mariadb -lmariadb";
  };

  # pre-commit hooks
  pre-commit.hooks = {
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
  '';
}
