"""Persistent local chat, skills, and agent workspace for YJ-64."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any


class ChatWorkspace:
    def __init__(self, user_data_dir: str | Path):
        self.root = Path(user_data_dir) / "yj64-workspace"
        self.root.mkdir(parents=True, exist_ok=True)
        self.chats_dir = self.root / "chats"
        self.agents_dir = self.root / "agents"
        self.histories_dir = self.root / "histories"
        for folder in (self.chats_dir, self.agents_dir, self.histories_dir):
            folder.mkdir(parents=True, exist_ok=True)
        self.skills_path = self.root / "skills.md"
        if not self.skills_path.exists():
            self.skills_path.write_text("# YJ-64 local skills\n", encoding="utf-8")
        self.index_path = self.root / "chats.json"
        if not self.index_path.exists():
            self._write_json(self.index_path, {"chats": []})
        if not self.list_chats():
            self.create_chat("Общий чат")

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)

    @staticmethod
    def _read_json(path: Path, fallback: Any) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return fallback

    def list_chats(self) -> list[dict[str, Any]]:
        data = self._read_json(self.index_path, {"chats": []})
        chats = data.get("chats", []) if isinstance(data, dict) else []
        return sorted([item for item in chats if isinstance(item, dict)], key=lambda x: x.get("updated_ms", 0), reverse=True)

    def create_chat(self, title: str, parent_id: str | None = None) -> str:
        chat_id = uuid.uuid4().hex
        chats = self.list_chats()
        chats.append({"id": chat_id, "title": str(title or "Новый чат"), "parent_id": parent_id, "created_ms": int(time.time() * 1000), "updated_ms": int(time.time() * 1000)})
        self._write_json(self.index_path, {"chats": chats})
        self.save_messages(chat_id, [])
        return chat_id

    def _messages_path(self, chat_id: str) -> Path:
        safe_id = "".join(c for c in str(chat_id) if c.isalnum() or c in "-_")
        if not safe_id:
            raise ValueError("Invalid chat id")
        return self.chats_dir / (safe_id + ".json")

    def load_messages(self, chat_id: str) -> list[dict[str, str]]:
        data = self._read_json(self._messages_path(chat_id), [])
        if not isinstance(data, list):
            return []
        return [{"role": str(x.get("role", "assistant")), "content": str(x.get("content", ""))} for x in data if isinstance(x, dict)]

    def save_messages(self, chat_id: str, messages: list[dict[str, Any]]) -> None:
        normalized = [{"role": str(x.get("role", "assistant")), "content": str(x.get("content", ""))} for x in messages if isinstance(x, dict)]
        self._write_json(self._messages_path(chat_id), normalized)
        chats = self.list_chats()
        now = int(time.time() * 1000)
        found = False
        for chat in chats:
            if str(chat.get("id")) == str(chat_id):
                chat["updated_ms"] = now
                if normalized:
                    first = next((m["content"] for m in normalized if m["role"] == "user" and m["content"].strip()), "")
                    if first and chat.get("title") in ("Общий чат", "Новый чат", "Untitled chat"):
                        chat["title"] = first[:48]
                found = True
                break
        if found:
            self._write_json(self.index_path, {"chats": chats})

    def _history_path(self, name: str) -> Path:
        key = "".join(c for c in str(name) if c.isalnum() or c in "-_ ").strip().replace(" ", "_")
        return self.histories_dir / ((key or "participant") + ".json")

    def load_named_history(self, name: str) -> list[dict[str, str]]:
        data = self._read_json(self._history_path(name), [])
        return [{"role": str(x.get("role", "assistant")), "content": str(x.get("content", ""))} for x in data if isinstance(x, dict)] if isinstance(data, list) else []

    def save_named_history(self, name: str, history: list[dict[str, Any]]) -> None:
        self._write_json(self._history_path(name), [{"role": str(x.get("role", "assistant")), "content": str(x.get("content", ""))} for x in history if isinstance(x, dict)])

    def read_skills(self) -> str:
        try:
            return self.skills_path.read_text(encoding="utf-8")
        except OSError:
            return ""

    def write_skills(self, text: str) -> None:
        self.skills_path.write_text(str(text), encoding="utf-8")

    def _agent_path(self, agent_id: str) -> Path:
        safe_id = "".join(c for c in str(agent_id) if c.isalnum() or c in "-_")
        if not safe_id:
            raise ValueError("Invalid agent id")
        return self.agents_dir / (safe_id + ".json")

    def create_agent(self, name: str, instructions: str, runner: str = "Participant 1") -> dict[str, Any]:
        agent = {"id": uuid.uuid4().hex, "name": str(name), "instructions": str(instructions), "runner": str(runner), "created_ms": int(time.time() * 1000), "private_messages": [], "code_candidate": "", "sandbox_status": "pending", "sandbox_note": ""}
        self.save_agent(agent)
        return agent

    def save_agent(self, agent: dict[str, Any]) -> None:
        if not isinstance(agent, dict) or not agent.get("id"):
            raise ValueError("Agent requires id")
        self._write_json(self._agent_path(str(agent["id"])), agent)

    def load_agent(self, agent_id: str) -> dict[str, Any] | None:
        data = self._read_json(self._agent_path(agent_id), None)
        return data if isinstance(data, dict) else None

    def list_agents(self) -> list[dict[str, Any]]:
        result = []
        for path in self.agents_dir.glob("*.json"):
            data = self._read_json(path, None)
            if isinstance(data, dict):
                result.append(data)
        return sorted(result, key=lambda x: x.get("created_ms", 0), reverse=True)

    def save_agent_message(self, agent_id: str, role: str, content: str) -> None:
        agent = self.load_agent(agent_id)
        if agent is None:
            return
        messages = agent.setdefault("private_messages", [])
        messages.append({"role": str(role), "content": str(content), "timestamp_ms": int(time.time() * 1000)})
        agent["private_messages"] = messages[-1000:]
        self.save_agent(agent)
