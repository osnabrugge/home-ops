#!/usr/bin/env python3
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

READ_TOOLS = {
    "codebase-memory-mcp": (
        "list_projects",
        "index_status",
        "search_graph",
        "get_code_snippet",
        "trace_path",
        "check_index_coverage",
    ),
    "memory-service": ("memory_search", "mistake_note_search"),
    "radar": (
        "issues",
        "diagnose",
        "get_resource",
        "get_events",
        "get_changes",
        "get_workload_logs",
        "discover_metrics",
        "query_prometheus",
        "wait_for",
    ),
}


def configured_servers(path: Path) -> set[str]:
    configuration = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(configuration, dict):
        raise ValueError("MCP configuration must be an object")
    servers = configuration.get("mcpServers")
    if not isinstance(servers, dict):
        raise ValueError("MCP configuration must contain an mcpServers object")
    return set(servers)


def make_command(target: str, servers: set[str]) -> list[str]:
    missing = READ_TOOLS.keys() - servers
    if missing:
        raise ValueError("Configure these existing MCP servers first: " + ", ".join(sorted(missing)))
    command = [
        "timeout", "--signal=TERM", "20m",
        "copilot", "-C", str(Path(__file__).resolve().parents[1]),
        "--agent", "home-ops-triage",
        "--trust-folder",
        "--disable-client-telemetry",
        "--sync-session=off",
        "--stream", "off",
        "--output-format", "json",
        "--log-level", "warning",
        "--no-ask-user",
        "--disable-builtin-mcps",
        "--deny-tool", "shell",
        "--deny-tool", "write",
    ]
    command.extend("--disable-mcp-server=" + name for name in sorted(servers - READ_TOOLS.keys()))
    for server, tools in READ_TOOLS.items():
        for tool in tools:
            command.extend(("--allow-tool", f"{server}({tool})"))
    command.append("--available-tools")
    command.extend(f"{server}-{tool}" for server, tools in READ_TOOLS.items() for tool in tools)
    command.extend((
        "-p",
        "Perform one read-only home-ops triage run for this target: " + target + "\n"
        "Use current MCP evidence and distinguish historical findings from active failures. "
        "Use only the explicitly available read-only MCP tools. Do not call shell, edit, "
        "mutation, issue-write, memory-write or other agents. Do not change identity after "
        "a denial. Do not implement, publish, restart or change permissions. Return the "
        "agent's concise evidence/escalation packet with actual UTC timestamps, measured "
        "status, explicitly no mutations, and the smallest next check or approval needed. "
        "If healthy, verify at least two actual check intervals. A blocked read or "
        "unperformed repair is ESCALATED, never RESOLVED. Do not print credentials.",
    ))
    return command


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run inherited-model, MCP-only read-only triage.")
    parser.add_argument("target", help="One alert name and affected resource, not additional CLI flags.")
    arguments = parser.parse_args(argv)
    if not arguments.target.strip():
        parser.error("Supply a nonempty alert/resource target")
    for executable in ("copilot", "timeout"):
        if shutil.which(executable) is None:
            parser.error(f"Required executable is missing: {executable}")
    try:
        servers = configured_servers(Path.home() / ".copilot" / "mcp-config.json")
        command = make_command(arguments.target, servers)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    result = subprocess.run(command, check=False)
    if result.returncode == 124:
        print("Triage exceeded twenty minutes; its outcome remains unresolved.", file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
