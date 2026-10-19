import sys

HELP = """\
usage: chronicle <command> [options]

Self-hosted, project-scoped memory for Claude Code, Cursor, and Codex.

Everyday:
  start [--port N] [--background]   start the dashboard (and Qdrant if semantic search is on)
  stop                              stop a backgrounded dashboard
  register NAME [--force]           register the current folder as a project
  setup AGENT --project NAME [--print]
                                    write the MCP config for AGENT, one of
                                    claude-desktop, claude-code, cursor, codex
  setup [--project NAME]            print the config for every agent instead
  update                            update this chronicle clone to the latest main

Search:
  semantic enable|disable|status    turn similarity search (Qdrant + model) on or off
  reindex [--project NAME]          rebuild the similarity index from your memories

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
        return version("chronicle-memory")
    except PackageNotFoundError:
        return "unknown"


def _serve(argv: list[str]) -> None:
    from chronicle.server import main as server_main

    server_main()


def _start(argv: list[str]) -> None:
    from chronicle import config, dashboard_cli, services

    if config.semantic_enabled():
        services.ensure_qdrant()
    dashboard_cli.main(["start", *argv])


def _stop(argv: list[str]) -> None:
    from chronicle import dashboard_cli

    dashboard_cli.main(["stop", *argv])


def _module_main(module_name: str, function: str = "main"):
    def run(argv: list[str]) -> None:
        import importlib

        getattr(importlib.import_module(f"chronicle.{module_name}"), function)(argv)

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
    "semantic": _module_main("semantic_cli"),
    "reindex": _module_main("semantic_cli", "reindex_main"),
}


def _stdin_is_terminal() -> bool:
    from chronicle.console import is_interactive

    return is_interactive(sys.stdin)


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
