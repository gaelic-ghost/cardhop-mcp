# cardhop-mcp

Local macOS MCP server for Cardhop using documented Cardhop integration routes:

- AppleScript: `tell application "Cardhop" to parse sentence "..."`
- URL scheme: `x-cardhop://parse?s=...`

`update` is intentionally implemented as a freeform alias over `parse` (no undocumented routes).

## Requirements

- macOS
- `uv`
- Python 3.13+

## Install dependencies

```bash
uv sync
```

## Run locally

```bash
uv run python app/server.py
```

## Codex MCP client config (example)

Add this server block to your Codex config (`$CODEX_HOME/config.toml`, usually `~/.codex/config.toml`):

```toml
[mcp_servers.cardhop]
enabled = true
command = "bash"
args = ["-lc", "cd /absolute/path/to/cardhop-mcp && PYTHONPATH=. uv run python app/server.py"]
```

## Exposed MCP tools

- `schema`: returns the locked schema bundle (`cardhop.mcp.tools.v1`)
- `parse`: send a sentence to Cardhop (`auto|applescript|url_scheme`, optional `add_immediately`, `dry_run`)
- `add`: convenience wrapper for parse with `add_immediately=true`
- `update`: freeform update guidance over parse semantics
- `healthcheck`: local readiness status for Cardhop + transport commands

## Update guidance

For best update behavior, use freeform instructions in this form:

- `"<existing name> <changed fields>"`
- Example: `Jane Doe new email jane@acme.com mobile 555-123-4567`

## Run tests

```bash
uv run pytest
```

## Project layout

- `app/server.py`: FastMCP server entrypoint
- `app/tools.py`: Cardhop schema and tool logic
- `tests/test_tools.py`: unit tests for parsing, transport, and health behavior
- `pyproject.toml`: project metadata and dependencies

## Development Quickstart

```bash
uv sync
uv run pytest
```

