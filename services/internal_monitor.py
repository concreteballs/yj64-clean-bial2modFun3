"""Embedded internal diagnostic agent for the YJ-64 base application."""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from urllib import request

from jnius import autoclass


SCHEMA = "yj64.diagnostic.v1"
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "bridge.json"


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def write_status(service: Any, payload: dict[str, Any]) -> None:
    path = Path(str(service.getFilesDir())) / "diagnostic-agent-status.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def spool_path(service: Any, filename: str) -> Path:
    return Path(str(service.getFilesDir())) / filename


def make_report(agent_id: str, event: str, **data: Any) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "agent": agent_id,
        "event": event,
        "timestamp_ms": int(time.time() * 1000),
        "report_id": uuid.uuid4().hex,
        "data": data,
    }


def append_spool(service: Any, path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(report, sort_keys=True) + "\n")


def send_bridge(config: dict[str, Any], report: dict[str, Any]) -> bool:
    """Send a report and retain a concise reason when Android IPC rejects it."""
    config["_last_bridge_error"] = ""
    try:
        bridge = config["bridge"]
        context = autoclass("org.kivy.android.PythonService").mService
        Uri = autoclass("android.net.Uri")
        Bundle = autoclass("android.os.Bundle")
        extras = Bundle()
        extras.putString("report_json", json.dumps(report, sort_keys=True))
        uri = Uri.parse("content://" + str(bridge["authority"]))
        result = context.getContentResolver().call(
            uri, str(bridge["method"]), None, extras
        )
        if result is None:
            config["_last_bridge_error"] = "provider_returned_null"
            return False
        report_id = str(report.get("report_id") or report.get("message_id") or "")
        accepted = (
            bool(report_id)
            and bool(result.getBoolean("ok", False))
            and str(result.getString("report_id") or "") == report_id
        )
        if not accepted:
            error_type = str(result.getString("error_type") or "ProviderRejected")
            error_message = str(result.getString("error") or "acknowledgement_mismatch")
            config["_last_bridge_error"] = f"{error_type}: {error_message}"
        return accepted
    except Exception as exc:
        config["_last_bridge_error"] = f"{type(exc).__name__}: {exc}"
        return False


def send_with_retry(config: dict[str, Any], report: dict[str, Any]) -> bool:
    # The provider acknowledges only after durable persistence. If unavailable,
    # the report is spooled and the tail-forwarder retries it later.
    return send_bridge(config, report)


def upload_https(
    endpoint: str,
    report: dict[str, Any],
    timeout: float = 5.0,
) -> bool:
    """Upload a report when a real HTTPS endpoint is configured."""

    if not endpoint:
        return False

    try:
        body = json.dumps(report).encode("utf-8")
        req = request.Request(
            endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=timeout) as response:
            return 200 <= int(response.status) < 300
    except (OSError, ValueError, TypeError):
        return False


def self_diagnostic(config: dict[str, Any], service: Any) -> dict[str, Any]:
    """Run deterministic startup checks before handing control to the base app."""

    checks: dict[str, Any] = {}

    try:
        config["agent_id"]
        config["target_package"]
        config["bridge"]["authority"]
        config["bridge"]["method"]
        checks["configuration"] = "ok"
    except (KeyError, TypeError):
        checks["configuration"] = "invalid"

    try:
        probe = Path(str(service.getFilesDir())) / ".diagnostic_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        checks["storage"] = "ok"
    except OSError:
        checks["storage"] = "unavailable"

    try:
        package_manager = service.getPackageManager()
        visible = (
            package_manager.getLaunchIntentForPackage(
                str(config["target_package"])
            )
            is not None
        )
        checks["target_visibility"] = (
            "visible" if visible else "not_visible"
        )
    except Exception as exc:
        checks["target_visibility"] = f"probe_error:{type(exc).__name__}"

    checks["process"] = "ok"
    return checks


def send_report_or_spool(
    config: dict[str, Any],
    service: Any,
    spool: Path,
    report: dict[str, Any],
) -> bool:
    """Prefer the external bridge and persist the report when it is unavailable."""

    bridge_ok = send_with_retry(config, report)
    if not bridge_ok:
        append_spool(service, spool, report)
        if report.get("event") != "bridge_delivery_failed":
            failure = make_report(
                str(config["agent_id"]),
                "bridge_delivery_failed",
                failed_report_id=str(report.get("report_id") or ""),
                failed_event=str(report.get("event") or ""),
                error=str(config.get("_last_bridge_error") or "unknown_ipc_failure"),
                fallback="local_jsonl_spool",
            )
            append_spool(service, spool, failure)

    endpoint = str(config["report"].get("https_endpoint", ""))
    if endpoint:
        upload_https(endpoint, report)

    return bridge_ok


def forward_spool_reports(
    config: dict[str, Any],
    spool: Path,
    offset: int,
) -> int:
    """Forward persisted base-app JSONL records in order; retain offset on failure."""
    if not spool.is_file():
        return 0
    bridge = config["bridge"]
    try:
        with spool.open("r", encoding="utf-8") as handle:
            handle.seek(offset)
            while True:
                line_start = handle.tell()
                line = handle.readline()
                if not line:
                    return handle.tell()
                try:
                    report = json.loads(line)
                except ValueError:
                    # Skip a malformed or partial record without blocking later lines.
                    offset = handle.tell()
                    continue
                if not isinstance(report, dict):
                    offset = handle.tell()
                    continue
                delivered = send_bridge(config, report)
                if not delivered:
                    return line_start
                offset = handle.tell()
    except OSError:
        return offset


def run() -> None:
    PythonService = autoclass("org.kivy.android.PythonService")
    service = PythonService.mService
    service.setAutoRestartService(True)

    config = load_config()
    agent_id = str(config["agent_id"])
    spool = spool_path(service, str(config["report"]["spool_filename"]))

    checks = self_diagnostic(config, service)
    self_report = make_report(
        agent_id,
        "self_diagnostic",
        checks=checks,
        target_package=config["target_package"],
    )
    self_bridge_ok = send_report_or_spool(config, service, spool, self_report)

    startup = make_report(
        agent_id,
        "internal_startup",
        pid=os.getpid(),
        python_version=sys.version.split()[0],
        target_package=config["target_package"],
        cwd=os.getcwd(),
        launch_strategy="service_runs_alongside_existing_base_activity",
    )
    startup_bridge_ok = send_report_or_spool(config, service, spool, startup)

    ready = make_report(
        agent_id,
        "internal_service_ready",
        target_package=config["target_package"],
        base_ui_relaunch_attempted=False,
        base_ui_should_remain_open=True,
        bridge_received_self_diagnostic=self_bridge_ok,
        bridge_received_startup=startup_bridge_ok,
    )
    ready_bridge_ok = send_report_or_spool(config, service, spool, ready)

    write_status(
        service,
        {
            "agent": agent_id,
            "event": "internal_service_ready",
            "bridge_status": (
                "connected"
                if self_bridge_ok or startup_bridge_ok or ready_bridge_ok
                else "spooled"
            ),
            "self_diagnostic": (
                "ok"
                if all(value in {"ok", "visible"} for value in checks.values())
                else json.dumps(checks, sort_keys=True)
            ),
            "target_launch": "not_relaunched_base_ui_kept_open",
            "target_success": True,
            "launch_report_sent": ready_bridge_ok,
        },
    )

    # Base and its service share the same app-private files directory.
    # Forward JSONL records to the standalone Monitor and retain the offset
    # while IPC is unavailable so records are retried after Monitor is installed/open.
    report_offset = 0
    while True:
        report_offset = forward_spool_reports(config, spool, report_offset)
        time.sleep(1.0)


run()
