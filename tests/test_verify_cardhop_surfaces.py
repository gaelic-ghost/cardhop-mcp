import datetime as dt

from scripts import verify_cardhop_surfaces as verify


def test_build_sentinel_uses_expected_prefix() -> None:
    sentinel = verify.build_sentinel(dt.datetime(2026, 3, 1, tzinfo=dt.UTC))
    assert sentinel.startswith("mcp_audit_")


def test_is_safe_test_record_requires_prefix_and_sentinel() -> None:
    sentinel = "mcp_audit_20260301000000"
    assert verify.is_safe_test_record("ZZZ MCP TEST Jane", f"note {sentinel}", sentinel)
    assert not verify.is_safe_test_record("Jane", f"note {sentinel}", sentinel)
    assert not verify.is_safe_test_record("ZZZ MCP TEST Jane", "note", sentinel)


def test_parse_contacts_rows_handles_tab_lines() -> None:
    raw = "id-1\tZZZ MCP TEST One\tmcp_audit_1\nid-2\tZZZ MCP TEST Two\tmcp_audit_2"
    rows = verify.parse_contacts_rows(raw)
    assert len(rows) == 2
    assert rows[0]["id"] == "id-1"
    assert rows[1]["name"] == "ZZZ MCP TEST Two"


def test_surface_matrix_includes_probe_metadata() -> None:
    capabilities = {
        "surfaces": [
            {
                "surface_id": "url_scheme.show",
                "documented": False,
                "verified_on_macos": False,
                "implementation_status": "missing",
                "support_level": "inconclusive",
                "evidence_ref": ["docs"],
                "notes": "candidate",
            }
        ]
    }
    probes = {
        "url_scheme.show": {
            "url": "x-cardhop://show",
            "ok": True,
            "returncode": 0,
            "stderr": "",
            "stdout": "",
        }
    }

    matrix = verify.surface_matrix(capabilities, probes)
    assert len(matrix) == 1
    assert matrix[0]["probe"]["ok"] is True
    assert "inconclusive" in matrix[0]["notes"]
