"""Secondary persistent event ledger and portable YJ-64 archive."""
from __future__ import annotations

import json
import os
import sqlite3
import time
import zipfile
from pathlib import Path
from typing import Any


class PersistentCore:
    def __init__(self, user_data_dir: str | Path):
        self.root = Path(user_data_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "yj64-persistent-core.sqlite3"
        self.workspace_path = self.root / "yj64-workspace"
        self.report_path = self.root / "yj64-reports" / "yj64-report.jsonl"
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp_ms INTEGER NOT NULL, event TEXT NOT NULL, data_json TEXT NOT NULL)")

    def _connect(self):
        db = sqlite3.connect(str(self.db_path), timeout=5)
        db.execute("PRAGMA journal_mode=WAL")
        return db

    def record_event(self, event: str, data: dict[str, Any] | None = None) -> None:
        try:
            with self._connect() as db:
                db.execute("INSERT INTO events(timestamp_ms,event,data_json) VALUES(?,?,?)", (int(time.time() * 1000), str(event), json.dumps(data or {}, ensure_ascii=False)))
        except sqlite3.Error:
            # The JSONL diagnostic report remains the primary event source.
            return

    def export_archive(self, destination: str | Path) -> Path:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp = destination.with_suffix(destination.suffix + ".tmp")
        manifest = {"schema": "yj64.archive.v1", "created_ms": int(time.time() * 1000), "files": []}
        with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in (self.workspace_path, self.report_path):
                if path.is_file():
                    arcname = str(path.relative_to(self.root))
                    archive.write(path, arcname)
                    manifest["files"].append(arcname)
                elif path.is_dir():
                    for child in path.rglob("*"):
                        if child.is_file() and not child.is_symlink():
                            arcname = str(child.relative_to(self.root))
                            archive.write(child, arcname)
                            manifest["files"].append(arcname)
            try:
                with self._connect() as db:
                    rows = db.execute("SELECT timestamp_ms,event,data_json FROM events ORDER BY id").fetchall()
                events_path = self.root / "yj64-events-export.json"
                events_path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
                archive.write(events_path, "yj64-events-export.json")
                events_path.unlink(missing_ok=True)
                manifest["files"].append("yj64-events-export.json")
            except sqlite3.Error:
                pass
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        if not zipfile.is_zipfile(temp) or temp.stat().st_size <= 0:
            temp.unlink(missing_ok=True)
            raise IOError("Archive validation failed: ZIP is empty or invalid")
        os.replace(temp, destination)
        return destination

    def import_archive(self, source: str | Path) -> int:
        source = Path(source)
        if not zipfile.is_zipfile(source):
            raise ValueError("Selected file is not a valid ZIP archive")
        allowed_roots = ("yj64-workspace/", "yj64-reports/")
        count = 0
        with zipfile.ZipFile(source, "r") as archive:
            bad = archive.testzip()
            if bad:
                raise ValueError("Archive integrity check failed: " + bad)
            names = archive.namelist()
            if "manifest.json" not in names:
                raise ValueError("Archive manifest is missing")
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            if not isinstance(manifest, dict) or manifest.get("schema") != "yj64.archive.v1":
                raise ValueError("Unsupported YJ-64 archive schema")
            declared = manifest.get("files")
            if not isinstance(declared, list) or not all(isinstance(name, str) for name in declared):
                raise ValueError("Archive manifest file list is missing or invalid")
            payloads = {
                info.filename: archive.read(info)
                for info in archive.infolist()
                if not info.is_dir() and info.filename not in {"manifest.json", "yj64-events-export.json"}
            }
            if set(declared) - {"yj64-events-export.json"} != set(payloads):
                raise ValueError("Archive contents do not match manifest file list")
            index_name = "yj64-workspace/chats.json"
            if index_name not in payloads:
                raise ValueError("Archive is incomplete: chat index is missing")
            try:
                index = json.loads(payloads[index_name].decode("utf-8"))
                chats = index.get("chats", []) if isinstance(index, dict) else []
                ids = [str(item.get("id", "")) for item in chats if isinstance(item, dict)]
                if not ids:
                    raise ValueError("Archive has no saved chat entries")
                for chat_id in ids:
                    safe_id = "".join(c for c in chat_id if c.isalnum() or c in "-_")
                    history_name = "yj64-workspace/chats/" + safe_id + ".json"
                    if not safe_id or history_name not in payloads:
                        raise ValueError("Archive is incomplete: chat history is missing")
                    history = json.loads(payloads[history_name].decode("utf-8"))
                    if not isinstance(history, list) or not all(
                        isinstance(item, dict) and "role" in item and "content" in item
                        for item in history
                    ):
                        raise ValueError("Archive contains invalid chat history JSON")
            except (UnicodeDecodeError, json.JSONDecodeError, AttributeError, TypeError) as exc:
                raise ValueError("Archive workspace JSON is invalid") from exc
            # Validate every destination before writing any content.
            for name in payloads:
                if not name.startswith(allowed_roots) or Path(name).is_absolute() or ".." in Path(name).parts:
                    raise ValueError("Archive contains an unsupported path")
            for name, payload in payloads.items():
                target = self.root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                temp = target.with_suffix(target.suffix + ".importing")
                temp.write_bytes(payload)
                os.replace(temp, target)
                count += 1
        return count
