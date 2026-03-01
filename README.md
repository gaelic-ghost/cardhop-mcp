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
- `capabilities`: runtime surface inventory with support levels and evidence refs

## Update guidance

For best update behavior, use freeform instructions in this form:

- `"<existing name> <changed fields>"`
- Example: `Jane Doe new email jane@acme.com mobile 555-123-4567`

## Run validation checks

```bash
uv run pytest
uv run ruff check .
uv run mypy .
```

## Surface verification audit

The repository includes a data-safe verifier for surface audits:

```bash
uv run python -m scripts.verify_cardhop_surfaces --mode readonly
uv run python -m scripts.verify_cardhop_surfaces --mode live-safe
```

- `readonly`: emits audit artifacts without mutating contacts.
- `live-safe`: uses sentinel-marked test contacts only (`ZZZ MCP TEST`, `mcp_audit_*`) and performs teardown.

Outputs:

- `artifacts/cardhop_surface_matrix.json`
- `artifacts/cardhop_test_data_manifest.json`
- `docs/evidence/cardhop-surface-map.md`
- `docs/cardhop-implementation-backlog.md`

## Project layout

- `app/server.py`: FastMCP server entrypoint
- `app/tools.py`: Cardhop schema and tool logic
- `tests/test_tools.py`: unit tests for parsing, transport, and health behavior
- `pyproject.toml`: project metadata and dependencies

## Development Quickstart

```bash
uv sync
uv run pytest
uv run ruff check .
uv run mypy .
```
