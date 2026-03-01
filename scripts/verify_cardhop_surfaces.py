from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from app.tools import cardhop_capabilities, cardhop_parse

REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = REPO_ROOT / "artifacts"
MATRIX_PATH = ARTIFACTS_DIR / "cardhop_surface_matrix.json"
MANIFEST_PATH = ARTIFACTS_DIR / "cardhop_test_data_manifest.json"

TEST_NAME_PREFIX = "ZZZ MCP TEST"


@dataclass
class CommandResult:
    ok: bool
    returncode: int
    stdout: str
    stderr: str


def _run(cmd: list[str]) -> CommandResult:
    completed = subprocess.run(cmd, check=False, capture_output=True, text=True)
    return CommandResult(
        ok=completed.returncode == 0,
        returncode=completed.returncode,
        stdout=(completed.stdout or "").strip(),
        stderr=(completed.stderr or "").strip(),
    )


def _run_osascript(script_lines: list[str]) -> CommandResult:
    cmd: list[str] = ["osascript"]
    for line in script_lines:
        cmd.extend(["-e", line])
    return _run(cmd)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def build_sentinel(now: dt.datetime | None = None) -> str:
    ts = (now or dt.datetime.now(dt.UTC)).strftime("%Y%m%d%H%M%S")
    return f"mcp_audit_{ts}"


def is_safe_test_record(name: str, note: str, sentinel: str) -> bool:
    return name.startswith(TEST_NAME_PREFIX) and sentinel in note


def parse_contacts_rows(raw: str) -> list[dict[str, str]]:
    if not raw:
        return []

    rows: list[dict[str, str]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        rows.append({"id": parts[0], "name": parts[1], "note": "\t".join(parts[2:])})
    return rows


def list_sentinel_contacts(sentinel: str) -> list[dict[str, str]]:
    safe_sentinel = _escape(sentinel)
    script = [
        'tell application "Contacts"',
        (
            'set matches to every person whose note contains "'
            + safe_sentinel
            + '" and name starts with "'
            + TEST_NAME_PREFIX
            + '"'
        ),
        "set outLines to {}",
        "repeat with p in matches",
        (
            'set end of outLines to (id of p as text) & tab & (name of p as text) '
            '& tab & (note of p as text)'
        ),
        "end repeat",
        "if (count of outLines) = 0 then return \"\"",
        "return outLines as text",
        "end tell",
    ]
    result = _run_osascript(script)
    if not result.ok:
        return []
    return parse_contacts_rows(result.stdout)


def create_sentinel_contact(sentinel: str) -> CommandResult:
    safe_sentinel = _escape(sentinel)
    suffix = sentinel.replace("mcp_audit_", "")
    script = [
        'tell application "Contacts"',
        (
            'set p to make new person with properties {first name:"ZZZ", '
            'last name:"MCP TEST '
            + _escape(suffix)
            + '"}'
        ),
        'set note of p to "' + safe_sentinel + '"',
        "save",
        "return id of p as text",
        "end tell",
    ]
    return _run_osascript(script)


def read_contact(contact_id: str) -> dict[str, str] | None:
    safe_id = _escape(contact_id)
    script = [
        'tell application "Contacts"',
        'set p to person id "' + safe_id + '"',
        'return (id of p as text) & tab & (name of p as text) & tab & (note of p as text)',
        "end tell",
    ]
    result = _run_osascript(script)
    if not result.ok or not result.stdout:
        return None
    rows = parse_contacts_rows(result.stdout)
    return rows[0] if rows else None


def update_contact_note(contact_id: str, sentinel: str, marker: str) -> CommandResult:
    contact = read_contact(contact_id)
    if contact is None:
        return CommandResult(False, 1, "", "Contact not found")
    if not is_safe_test_record(contact["name"], contact["note"], sentinel):
        return CommandResult(False, 1, "", "Safety guard prevented non-test update")

    safe_id = _escape(contact_id)
    updated_note = _escape(f"{contact['note']} {marker}".strip())
    script = [
        'tell application "Contacts"',
        'set p to person id "' + safe_id + '"',
        'set note of p to "' + updated_note + '"',
        "save",
        "return id of p as text",
        "end tell",
    ]
    return _run_osascript(script)


def delete_contact(contact_id: str, sentinel: str) -> CommandResult:
    contact = read_contact(contact_id)
    if contact is None:
        return CommandResult(True, 0, "", "")
    if not is_safe_test_record(contact["name"], contact["note"], sentinel):
        return CommandResult(False, 1, "", "Safety guard prevented non-test delete")

    safe_id = _escape(contact_id)
    script = [
        'tell application "Contacts"',
        'set p to person id "' + safe_id + '"',
        "delete p",
        "save",
        "return \"deleted\"",
        "end tell",
    ]
    return _run_osascript(script)


def read_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        return {}
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return cast(dict[str, Any], data)
    return {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def probe_url(url: str) -> dict[str, Any]:
    result = _run(["open", url])
    return {
        "url": url,
        "ok": result.ok,
        "returncode": result.returncode,
        "stderr": result.stderr,
        "stdout": result.stdout,
    }


def verify_candidate_routes() -> dict[str, Any]:
    candidates = {
        "url_scheme.show": "x-cardhop://show",
        "url_scheme.preferences": "x-cardhop://preferences",
        "url_scheme.x_callback_url": "x-cardhop://x-callback-url/show",
        "url_scheme.list_param": "x-cardhop://parse?s=ZZZ%20MCP%20TEST&list=default",
        "url_scheme.add_param": "x-cardhop://parse?s=ZZZ%20MCP%20TEST&add=1",
    }
    return {surface_id: probe_url(url) for surface_id, url in candidates.items()}


def surface_matrix(
    capabilities: dict[str, Any], route_probes: dict[str, Any]
) -> list[dict[str, Any]]:
    rows = []
    by_id: dict[str, dict[str, Any]] = {
        str(surface["surface_id"]): surface for surface in capabilities.get("surfaces", [])
    }

    for surface_id, base in by_id.items():
        row = {
            "surface_id": surface_id,
            "documented": bool(base.get("documented", False)),
            "verified_on_macos": bool(base.get("verified_on_macos", False)),
            "implementation_status": base.get("implementation_status", "missing"),
            "support_level": base.get("support_level", "inconclusive"),
            "evidence": base.get("evidence_ref", []),
            "notes": base.get("notes", ""),
        }
        probe = route_probes.get(surface_id)
        if probe is not None:
            row["probe"] = probe
            if probe.get("ok"):
                row["notes"] = (
                    str(row["notes"])
                    + " URL probe launched successfully; behavior remains inconclusive."
                ).strip()
        rows.append(row)

    rows.sort(key=lambda item: item["surface_id"])
    return rows


def run_live_safe_data_lifecycle(sentinel: str) -> dict[str, Any]:
    created_ids: list[str] = []
    touched_ids: list[str] = []
    operations: list[dict[str, Any]] = []

    existing = list_sentinel_contacts(sentinel)
    if existing:
        contact_id = existing[0]["id"]
        touched_ids.append(contact_id)
        operations.append({"action": "reuse_existing", "contact_id": contact_id, "ok": True})
    else:
        created = create_sentinel_contact(sentinel)
        contact_id = created.stdout.strip()
        if created.ok and contact_id:
            created_ids.append(contact_id)
            touched_ids.append(contact_id)
        operations.append(
            {
                "action": "create",
                "ok": created.ok,
                "contact_id": contact_id,
                "stderr": created.stderr,
            }
        )

    read_ok = False
    if touched_ids:
        current = read_contact(touched_ids[0])
        read_ok = (
            current is not None
            and is_safe_test_record(current["name"], current["note"], sentinel)
        )
        operations.append({"action": "read", "ok": read_ok, "contact": current})

    update_ok = False
    if touched_ids:
        updated = update_contact_note(touched_ids[0], sentinel, "verified")
        update_ok = updated.ok
        operations.append({"action": "update", "ok": updated.ok, "stderr": updated.stderr})

    deleted_ids: list[str] = []
    for contact_id in list(touched_ids):
        deleted = delete_contact(contact_id, sentinel)
        if deleted.ok:
            deleted_ids.append(contact_id)
        operations.append(
            {
                "action": "delete",
                "ok": deleted.ok,
                "contact_id": contact_id,
                "stderr": deleted.stderr,
            }
        )

    residual = list_sentinel_contacts(sentinel)
    cleanup_ok = len(residual) == 0

    return {
        "sentinel": sentinel,
        "created_record_ids": created_ids,
        "touched_record_ids": touched_ids,
        "deleted_record_ids": deleted_ids,
        "operations": operations,
        "read_ok": read_ok,
        "update_ok": update_ok,
        "cleanup": {
            "ok": cleanup_ok,
            "residual_count": len(residual),
            "residual_ids": [row["id"] for row in residual],
        },
    }


def perform_residual_cleanup(previous_manifest: dict[str, Any]) -> dict[str, Any]:
    pending = previous_manifest.get("pending_cleanup", [])
    if not isinstance(pending, list):
        return {"attempted": False, "deleted_ids": [], "errors": []}

    deleted_ids: list[str] = []
    errors: list[str] = []
    for item in pending:
        if not isinstance(item, dict):
            continue
        contact_id = str(item.get("contact_id", "")).strip()
        sentinel = str(item.get("sentinel", "")).strip()
        if not contact_id or not sentinel:
            continue
        result = delete_contact(contact_id, sentinel)
        if result.ok:
            deleted_ids.append(contact_id)
        else:
            errors.append(f"{contact_id}: {result.stderr}")

    return {"attempted": True, "deleted_ids": deleted_ids, "errors": errors}


def run(mode: str) -> int:
    now = dt.datetime.now(dt.UTC)
    sentinel = build_sentinel(now)

    previous_manifest = read_manifest()
    residual_cleanup = perform_residual_cleanup(previous_manifest)

    capabilities = cardhop_capabilities()
    dry_sentence = f"{TEST_NAME_PREFIX} readonly {sentinel}"
    dry_parse = cardhop_parse(
        sentence=dry_sentence,
        transport="auto",
        add_immediately=True,
        dry_run=True,
    )

    route_probes = verify_candidate_routes()
    matrix_rows = surface_matrix(capabilities, route_probes)

    matrix_payload = {
        "generated_at_utc": now.isoformat(),
        "mode": mode,
        "schema_version": capabilities.get("schema_version"),
        "cloud_api": capabilities.get("cloud_api"),
        "rows": matrix_rows,
    }
    write_json(MATRIX_PATH, matrix_payload)

    manifest_payload: dict[str, Any] = {
        "generated_at_utc": now.isoformat(),
        "mode": mode,
        "sentinel": sentinel,
        "dry_run_parse": dry_parse,
        "residual_cleanup": residual_cleanup,
        "pending_cleanup": [],
        "live_safe": {
            "executed": False,
            "created_record_ids": [],
            "touched_record_ids": [],
            "deleted_record_ids": [],
            "cleanup": {"ok": True, "residual_count": 0, "residual_ids": []},
            "operations": [],
        },
    }

    if mode == "live-safe":
        lifecycle = run_live_safe_data_lifecycle(sentinel)
        manifest_payload["live_safe"] = {
            "executed": True,
            **lifecycle,
        }

        residual_ids = lifecycle["cleanup"].get("residual_ids", [])
        pending_cleanup = [
            {"contact_id": contact_id, "sentinel": sentinel} for contact_id in residual_ids
        ]
        manifest_payload["pending_cleanup"] = pending_cleanup

    write_json(MANIFEST_PATH, manifest_payload)

    print(f"wrote {MATRIX_PATH}")
    print(f"wrote {MANIFEST_PATH}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify Cardhop macOS surfaces with readonly or live-safe checks."
    )
    parser.add_argument(
        "--mode",
        choices=["readonly", "live-safe"],
        default="readonly",
        help="Verification mode. live-safe is sentinel-guarded and performs teardown.",
    )
    args = parser.parse_args()
    return run(args.mode)


if __name__ == "__main__":
    raise SystemExit(main())
