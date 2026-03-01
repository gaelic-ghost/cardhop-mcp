# Cardhop Implementation Backlog

## Prioritization Rules

- P0: documented + verified + missing
- P1: documented + partial
- P2: verified but undocumented (experimental)

## Current Gap Summary

The current MCP server already implements documented macOS parse routes (`applescript.parse_sentence`, `url_scheme.parse`) and add/update wrappers.

Live-safe verification has been executed successfully on 2026-03-01 with sentinel-only CRUD and teardown validation.

### P0

- None currently identified from baseline documented surfaces.

### P1

- Add explicit capabilities introspection for surface-level support status and evidence references.
  - Status: implemented in this branch via `capabilities` tool and schema extension.

### P2

- `macos.service.send_to_cardhop`
  - Why: Accessible from app metadata but not officially documented as MCP transport.
  - Suggested approach: keep behind explicit experimental namespace if added.
- Candidate iOS URL routes (`show`, `preferences`, `x-callback-url`, `list`, `add`)
  - Why: Publicly documented for iOS; not verified as stable/supported on macOS.
  - Suggested approach: only implement route-specific MCP tools after reproducible macOS verification.

## Cloud/API Track

- Conclusion: `no_public_api_found` for a direct Cardhop public API.
- Public integration/account routes exist and should be tracked separately from local execution transports.

## Next Implementation Steps

1. Re-run `scripts/verify_cardhop_surfaces.py --mode live-safe` after Cardhop/Flexibits or macOS upgrades to detect behavior drift.
2. If any iOS routes prove stable on macOS, add route-specific MCP tools with explicit `experimental` support labeling first.
3. Add optional integration-adapter docs for account/platform integrations, separate from local transport tools.
