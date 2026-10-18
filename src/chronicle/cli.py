import sys

HELP = """\
usage: chronicle <command> [options]

Self-hosted, project-scoped memory for Claude Code, Cursor, and Codex.

Everyday:
  start [--port N] [--background]   start Qdrant (if needed) and the dashboard
  stop                              stop a backgrounded dashboard
  register --project NAME           register the current folder as a project
  setup [--project NAME]            print MCP config for Claude Code, Cursor, Codex
  update                            update this chronicle clone to the latest main

Memories:
  import PATH --project NAME --type TYPE
                                    bulk-load a file or folder of .md/.txt files
  graph [--project NAME | --all] [--cross-project]
        [--min-similarity N] [--out FILE]
                                    write and open a 3D memory graph
  eval --project NAME               report on a project's memory quality

Scopes:
  scope create PATH                 create a scope (and any missing parents)
  scope list [--prefix PATH]        print the scope tree
  scope move PATH [--to PARENT]     move a scope under a new parent

Dashboard:
  dashboard start [--port N] [--background]
                                    start only the dashboard
  dashboard stop                    stop a backgrounded dashboard

Server:
  serve                             run the MCP server over stdio (what MCP
                                    clients launch; plain `chronicle` does the
                                    same when not run from a terminal)

Memory types: architecture, bug, checkpoint, decision, note, overview, todo

Run `chronicle <command> --help` for a command's full options.
"""


def _version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("chronicle")
    except PackageNotFoundError:
        return "unknown"


def _serve(argv: list[str]) -> None:
    from chronicle.server import main as server_main

    server_main()


def _start(argv: list[str]) -> None:
    from chronicle import dashboard_cli, services

    services.ensure_qdrant()
    dashboard_cli.main(["start", *argv])


def _stop(argv: list[str]) -> None:
    from chronicle import dashboard_cli

    dashboard_cli.main(["stop", *argv])


def _module_main(module_name: str):
    def run(argv: list[str]) -> None:
        import importlib

        importlib.import_module(f"chronicle.{module_name}").main(argv)

    return run


COMMANDS = {
    "start": _start,
    "stop": _stop,
    "serve": _serve,
    "import": _module_main("import_cli"),
    "graph": _module_main("graph_cli"),
    "setup": _module_main("setup_cli"),
    "register": _module_main("register_cli"),
    "scope": _module_main("scope_cli"),
    "dashboard": _module_main("dashboard_cli"),
    "eval": _module_main("eval_cli"),
    "update": _module_main("update_cli"),
}


def _stdin_is_terminal() -> bool:
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


def main() -> None:
    from chronicle.console import use_utf8_output

    use_utf8_output()
    args = sys.argv[1:]

    if not args:
        # MCP clients (Claude Code, Cursor, Codex, Claude Desktop) launch a
        # bare `chronicle` with stdin piped, so that still starts the server;
        # a person typing it in a terminal gets the command list instead.
        if _stdin_is_terminal():
            from chronicle import services

            print(HELP)
            for line in services.status_lines():
                print(line)
            return
        print(
            "chronicle: starting the MCP server on stdio (waiting for a client). "
            "Run `chronicle --help` for commands.",
            file=sys.stderr,
        )
        _serve([])
        return

    command, rest = args[0], args[1:]
    if command in ("-h", "--help", "help"):
        print(HELP, end="")
        return
    if command in ("-V", "--version", "version"):
        print(f"chronicle {_version()}")
        return

    handler = COMMANDS.get(command)
    if handler is None:
        print(f"chronicle: unknown command '{command}'\n", file=sys.stderr)
        print(HELP, end="", file=sys.stderr)
        raise SystemExit(2)
    handler(rest)
