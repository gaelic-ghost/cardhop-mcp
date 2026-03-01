from __future__ import annotations

import datetime as dt
import os
import plistlib
import shutil
import subprocess
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from typing import Annotated, Literal
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field

Transport = Literal["auto", "applescript", "url_scheme"]
ResolvedTransport = Literal["applescript", "url_scheme"]
ErrorCode = Literal[
    "CARDHOP_NOT_FOUND",
    "AUTOMATION_DENIED",
    "INVALID_INPUT",
    "LAUNCH_FAILED",
    "EXEC_FAILED",
]
SupportLevel = Literal["documented", "verified", "experimental", "inconclusive"]
ImplementationStatus = Literal["implemented", "partial", "missing", "not_applicable"]

MAX_SENTENCE_LENGTH = 2000
CARDHOP_APP_PATHS = (
    "/Applications/Cardhop.app",
    os.path.expanduser("~/Applications/Cardhop.app"),
)


class DispatchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    dispatched: bool
    command_preview: str
    dry_run: bool
    error_code: ErrorCode | None = None
    error_message: str | None = None
    transport_used: ResolvedTransport | None = None


class HealthcheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    cardhop_installed: bool
    applescript_available: bool
    url_scheme_available: bool
    notes: list[str]


class SurfaceCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    surface_id: str
    documented: bool
    verified_on_macos: bool
    implementation_status: ImplementationStatus
    support_level: SupportLevel
    evidence_ref: list[str]
    notes: str


class CloudApiStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    applicable: bool
    status: Literal["public_api_found", "no_public_api_found", "inconclusive"]
    notes: str
    evidence_ref: list[str]


class CapabilitiesResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    schema_version: str
    audited_at_utc: str
    cardhop_installed: bool
    cardhop_version: str | None
    cloud_api: CloudApiStatus
    surfaces: list[SurfaceCapability]
    notes: list[str]


CARDHOP_SCHEMA_BUNDLE: dict[str, object] = {
    "$id": "cardhop.mcp.tools.v1",
    "version": "1.1.0",
    "constraints": {
        "documented_macos_routes_only": True,
        "allowed_transports": ["applescript.parse_sentence", "url_scheme.parse"],
        "support_levels": ["documented", "verified", "experimental", "inconclusive"],
    },
    "tools": [
        "cardhop_parse",
        "cardhop_add",
        "cardhop_update",
        "cardhop_healthcheck",
        "cardhop_capabilities",
    ],
    "metadata": {
        "surface_inventory_fields": [
            "surface_id",
            "documented",
            "verified_on_macos",
            "implementation_status",
            "support_level",
            "evidence_ref",
        ],
        "cloud_api_status_field": "public_api_found|no_public_api_found|inconclusive",
    },
}


def _is_cardhop_installed() -> bool:
    return any(os.path.isdir(path) for path in CARDHOP_APP_PATHS)


def _cardhop_app_path() -> str | None:
    for path in CARDHOP_APP_PATHS:
        if os.path.isdir(path):
            return path
    return None


def _which(command: str) -> bool:
    return shutil.which(command) is not None


def _read_cardhop_info_plist() -> dict[str, object]:
    app_path = _cardhop_app_path()
    if app_path is None:
        return {}

    plist_path = os.path.join(app_path, "Contents", "Info.plist")
    if not os.path.isfile(plist_path):
        return {}

    with open(plist_path, "rb") as handle:
        raw = plistlib.load(handle)
    return raw if isinstance(raw, dict) else {}


def _read_cardhop_sdef() -> str:
    app_path = _cardhop_app_path()
    if app_path is None:
        return ""

    sdef_path = os.path.join(app_path, "Contents", "Resources", "Cardhop.sdef")
    if not os.path.isfile(sdef_path):
        return ""

    with open(sdef_path, encoding="utf-8") as handle:
        return handle.read()


def _has_applescript_parse_sentence(sdef_text: str) -> bool:
    if not sdef_text:
        return False
    try:
        root = ET.fromstring(sdef_text)
    except ET.ParseError:
        return False
    return any(
        element.attrib.get("name") == "parse sentence"
        for element in root.findall(".//command")
    )


def _has_applescript_add_immediately(sdef_text: str) -> bool:
    if not sdef_text:
        return False
    try:
        root = ET.fromstring(sdef_text)
    except ET.ParseError:
        return False

    for command in root.findall(".//command"):
        if command.attrib.get("name") != "parse sentence":
            continue
        for parameter in command.findall(".//parameter"):
            if parameter.attrib.get("name") == "add immediately":
                return True
    return False


def _plist_has_url_scheme(info: dict[str, object], scheme: str) -> bool:
    url_types = info.get("CFBundleURLTypes")
    if not isinstance(url_types, list):
        return False

    for entry in url_types:
        if not isinstance(entry, dict):
            continue
        schemes = entry.get("CFBundleURLSchemes")
        if isinstance(schemes, list) and any(value == scheme for value in schemes):
            return True
    return False


def _plist_has_send_to_cardhop_service(info: dict[str, object]) -> bool:
    services = info.get("NSServices")
    if not isinstance(services, list):
        return False

    for service in services:
        if not isinstance(service, dict):
            continue
        if service.get("NSMessage") == "sendToCardhop":
            return True
    return False


def _escape_applescript(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _applescript_preview(sentence: str, add_immediately: bool) -> str:
    escaped_sentence = _escape_applescript(sentence)
    tail = " with add immediately" if add_immediately else ""
    return f'tell application "Cardhop" to parse sentence "{escaped_sentence}"{tail}'


def _url_preview(sentence: str) -> str:
    return f"x-cardhop://parse?s={quote(sentence, safe='')}"


def _run(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, capture_output=True, text=True)


def _validate_sentence(raw_sentence: str) -> str:
    sentence = raw_sentence.strip()
    if not sentence:
        raise ValueError("sentence must not be empty")
    if len(sentence) > MAX_SENTENCE_LENGTH:
        raise ValueError(f"sentence must be <= {MAX_SENTENCE_LENGTH} characters")
    return sentence


def _resolve_transport(
    requested: Transport,
) -> tuple[ResolvedTransport | None, DispatchResult | None]:
    if not _is_cardhop_installed():
        return None, DispatchResult(
            ok=False,
            dispatched=False,
            dry_run=False,
            command_preview="",
            error_code="CARDHOP_NOT_FOUND",
            error_message="Cardhop.app not found in /Applications or ~/Applications.",
        )

    has_osascript = _which("osascript")
    has_open = _which("open")

    if requested == "applescript":
        if not has_osascript:
            return None, DispatchResult(
                ok=False,
                dispatched=False,
                dry_run=False,
                command_preview="",
                error_code="EXEC_FAILED",
                error_message="osascript is not available on PATH.",
            )
        return "applescript", None

    if requested == "url_scheme":
        if not has_open:
            return None, DispatchResult(
                ok=False,
                dispatched=False,
                dry_run=False,
                command_preview="",
                error_code="EXEC_FAILED",
                error_message="open is not available on PATH.",
            )
        return "url_scheme", None

    if has_osascript:
        return "applescript", None
    if has_open:
        return "url_scheme", None
    return None, DispatchResult(
        ok=False,
        dispatched=False,
        dry_run=False,
        command_preview="",
        error_code="EXEC_FAILED",
        error_message="Neither osascript nor open is available on PATH.",
    )


def _dispatch_applescript(sentence: str, add_immediately: bool, dry_run: bool) -> DispatchResult:
    preview = _applescript_preview(sentence, add_immediately)
    if dry_run:
        return DispatchResult(
            ok=True,
            dispatched=False,
            dry_run=True,
            command_preview=preview,
            transport_used="applescript",
        )

    completed = _run(["osascript", "-e", preview])
    if completed.returncode == 0:
        return DispatchResult(
            ok=True,
            dispatched=True,
            dry_run=False,
            command_preview=preview,
            transport_used="applescript",
        )

    stderr = (completed.stderr or "").strip()
    denied_hint = "not authorized" in stderr.lower() or "not permitted" in stderr.lower()
    return DispatchResult(
        ok=False,
        dispatched=False,
        dry_run=False,
        command_preview=preview,
        transport_used="applescript",
        error_code="AUTOMATION_DENIED" if denied_hint else "EXEC_FAILED",
        error_message=stderr or "osascript execution failed.",
    )


def _dispatch_url_scheme(sentence: str, dry_run: bool) -> DispatchResult:
    url = _url_preview(sentence)
    if dry_run:
        return DispatchResult(
            ok=True,
            dispatched=False,
            dry_run=True,
            command_preview=url,
            transport_used="url_scheme",
        )

    completed = _run(["open", url])
    if completed.returncode == 0:
        return DispatchResult(
            ok=True,
            dispatched=True,
            dry_run=False,
            command_preview=url,
            transport_used="url_scheme",
        )

    stderr = (completed.stderr or "").strip()
    return DispatchResult(
        ok=False,
        dispatched=False,
        dry_run=False,
        command_preview=url,
        transport_used="url_scheme",
        error_code="LAUNCH_FAILED",
        error_message=stderr or "open command failed for Cardhop URL scheme.",
    )


def cardhop_parse(
    sentence: Annotated[str, Field(min_length=1, max_length=MAX_SENTENCE_LENGTH)],
    transport: Transport = "auto",
    add_immediately: bool = False,
    dry_run: bool = False,
) -> dict[str, object]:
    """Send a natural-language sentence to Cardhop via documented macOS parse routes.

    Uses only:
    - AppleScript: tell application "Cardhop" to parse sentence "..."
    - URL scheme: x-cardhop://parse?s=...
    """
    try:
        clean_sentence = _validate_sentence(sentence)
    except ValueError as exc:
        return DispatchResult(
            ok=False,
            dispatched=False,
            dry_run=dry_run,
            command_preview="",
            error_code="INVALID_INPUT",
            error_message=str(exc),
        ).model_dump()

    resolved_transport, error = _resolve_transport(transport)
    if error is not None:
        error.dry_run = dry_run
        return error.model_dump()

    assert resolved_transport is not None
    if resolved_transport == "applescript":
        return _dispatch_applescript(
            clean_sentence,
            add_immediately=add_immediately,
            dry_run=dry_run,
        ).model_dump()
    return _dispatch_url_scheme(clean_sentence, dry_run=dry_run).model_dump()


def cardhop_add(
    sentence: Annotated[str, Field(min_length=1, max_length=MAX_SENTENCE_LENGTH)],
    transport: Transport = "auto",
    dry_run: bool = False,
) -> dict[str, object]:
    """Convenience wrapper for add/create flows using Cardhop parse.

    This always maps to parse with add_immediately=true.
    """
    return cardhop_parse(
        sentence=sentence,
        transport=transport,
        add_immediately=True,
        dry_run=dry_run,
    )


def cardhop_update(
    instruction: Annotated[str, Field(min_length=1, max_length=MAX_SENTENCE_LENGTH)],
    transport: Transport = "auto",
    add_immediately: bool = False,
    dry_run: bool = False,
) -> dict[str, object]:
    """Freeform update/edit command over Cardhop parse.

    Guidance for LLMs:
    - Use natural language updates in the form '<existing name> <changed fields>'.
    - Example: 'Jane Doe new email jane@acme.com mobile 555-123-4567'.
    - Do not rely on undocumented Cardhop routes or identifiers.
    """
    return cardhop_parse(
        sentence=instruction,
        transport=transport,
        add_immediately=add_immediately,
        dry_run=dry_run,
    )


def cardhop_healthcheck() -> dict[str, object]:
    """Check Cardhop and local transport readiness for macOS."""
    cardhop_installed = _is_cardhop_installed()
    applescript_available = _which("osascript")
    url_scheme_available = _which("open")

    notes = []
    if not cardhop_installed:
        notes.append("Install Cardhop.app in /Applications or ~/Applications.")
    if applescript_available:
        notes.append(
            "AppleScript transport available; first run may prompt for Automation permission."
        )
    if url_scheme_available:
        notes.append("URL scheme transport available via open x-cardhop://parse.")
    if not applescript_available and not url_scheme_available:
        notes.append("No supported transport command available on PATH.")

    payload = HealthcheckResult(
        ok=cardhop_installed and (applescript_available or url_scheme_available),
        cardhop_installed=cardhop_installed,
        applescript_available=applescript_available,
        url_scheme_available=url_scheme_available,
        notes=notes,
    )
    return payload.model_dump()


def cardhop_capabilities() -> dict[str, object]:
    """Return runtime-discovered Cardhop surface capabilities for this host."""
    cardhop_installed = _is_cardhop_installed()
    has_osascript = _which("osascript")
    has_open = _which("open")

    info = _read_cardhop_info_plist()
    sdef_text = _read_cardhop_sdef()
    parse_sentence_in_sdef = _has_applescript_parse_sentence(sdef_text)
    add_immediately_in_sdef = _has_applescript_add_immediately(sdef_text)
    cardhop_version = info.get("CFBundleShortVersionString")
    if not isinstance(cardhop_version, str):
        cardhop_version = None

    x_cardhop_registered = _plist_has_url_scheme(info, "x-cardhop")
    send_service_registered = _plist_has_send_to_cardhop_service(info)
    docs_mac = "https://flexibits.com/cardhop-mac/help/integration"
    docs_ios = "https://flexibits.com/cardhop-ios/help/integration"
    docs_integrations = "https://flexibits.com/cardhop/integrations"
    docs_account_integrations = "https://flexibits.com/account/help/integrations"

    surfaces = [
        SurfaceCapability(
            surface_id="applescript.parse_sentence",
            documented=True,
            verified_on_macos=cardhop_installed and has_osascript and parse_sentence_in_sdef,
            implementation_status="implemented",
            support_level="verified" if parse_sentence_in_sdef else "inconclusive",
            evidence_ref=[docs_mac, "local_sdef:command=parse sentence"],
            notes="Primary documented AppleScript command.",
        ),
        SurfaceCapability(
            surface_id="applescript.add_immediately",
            documented=True,
            verified_on_macos=cardhop_installed and has_osascript and add_immediately_in_sdef,
            implementation_status="implemented",
            support_level="verified" if add_immediately_in_sdef else "inconclusive",
            evidence_ref=[docs_mac, "local_sdef:parameter=add immediately"],
            notes="Optional parse modifier to immediately save parsed data.",
        ),
        SurfaceCapability(
            surface_id="url_scheme.parse",
            documented=True,
            verified_on_macos=cardhop_installed and has_open and x_cardhop_registered,
            implementation_status="implemented",
            support_level="verified" if x_cardhop_registered else "inconclusive",
            evidence_ref=[docs_mac, "local_plist:CFBundleURLSchemes=x-cardhop"],
            notes="Documented x-cardhop parse route on macOS.",
        ),
        SurfaceCapability(
            surface_id="url_scheme.show",
            documented=False,
            verified_on_macos=False,
            implementation_status="missing",
            support_level="inconclusive",
            evidence_ref=[docs_ios],
            notes="Documented for iOS; no verified macOS support signal yet.",
        ),
        SurfaceCapability(
            surface_id="url_scheme.preferences",
            documented=False,
            verified_on_macos=False,
            implementation_status="missing",
            support_level="inconclusive",
            evidence_ref=[docs_ios],
            notes="Documented for iOS; no verified macOS support signal yet.",
        ),
        SurfaceCapability(
            surface_id="url_scheme.x_callback_url",
            documented=False,
            verified_on_macos=False,
            implementation_status="missing",
            support_level="inconclusive",
            evidence_ref=[docs_ios],
            notes="Documented for iOS; not currently verified on macOS.",
        ),
        SurfaceCapability(
            surface_id="url_scheme.list_param",
            documented=False,
            verified_on_macos=False,
            implementation_status="missing",
            support_level="inconclusive",
            evidence_ref=[docs_ios],
            notes="iOS URL parameter candidate; not verified on macOS.",
        ),
        SurfaceCapability(
            surface_id="url_scheme.add_param",
            documented=False,
            verified_on_macos=False,
            implementation_status="missing",
            support_level="inconclusive",
            evidence_ref=[docs_ios],
            notes="iOS URL parameter candidate; not verified on macOS.",
        ),
        SurfaceCapability(
            surface_id="macos.service.send_to_cardhop",
            documented=False,
            verified_on_macos=cardhop_installed and send_service_registered,
            implementation_status="missing",
            support_level="experimental",
            evidence_ref=["local_plist:NSServices.sendToCardhop"],
            notes="Accessible via macOS Services menu; not exposed by current MCP toolset.",
        ),
        SurfaceCapability(
            surface_id="automation.shortcuts_app_intents",
            documented=True,
            verified_on_macos=False,
            implementation_status="missing",
            support_level="inconclusive",
            evidence_ref=["https://flexibits.com/cardhop"],
            notes="Public product docs advertise Shortcuts support; callable surface TBD.",
        ),
        SurfaceCapability(
            surface_id="cloud.integrations.account_platform",
            documented=True,
            verified_on_macos=False,
            implementation_status="not_applicable",
            support_level="documented",
            evidence_ref=[docs_integrations, docs_account_integrations],
            notes="Public integrations exist but are outside direct local transport execution.",
        ),
    ]

    notes = [
        "Cloud API status is based on publicly documented surfaces only.",
        "Undocumented routes are tracked as inconclusive unless verified on macOS.",
    ]
    payload = CapabilitiesResult(
        ok=cardhop_installed and (has_osascript or has_open),
        schema_version=str(CARDHOP_SCHEMA_BUNDLE["version"]),
        audited_at_utc=dt.datetime.now(dt.UTC).isoformat(),
        cardhop_installed=cardhop_installed,
        cardhop_version=cardhop_version,
        cloud_api=CloudApiStatus(
            applicable=False,
            status="no_public_api_found",
            notes="No publicly documented Cardhop REST/GraphQL API was identified.",
            evidence_ref=[docs_integrations, docs_account_integrations],
        ),
        surfaces=surfaces,
        notes=notes,
    )
    return payload.model_dump()
