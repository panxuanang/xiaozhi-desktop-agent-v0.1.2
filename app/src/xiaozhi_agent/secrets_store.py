from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from .paths import SECRETS_FILE


class SecretStore:
    """Small Windows DPAPI-backed secret store.

    The encrypted bytes are scoped to the current Windows user. A base64 fallback
    exists only so tests can run off Windows; production Windows uses DPAPI.
    """

    def __init__(self, path: Path = SECRETS_FILE):
        self.path = path

    def _load(self) -> dict[str, str]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save(self, data: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    @staticmethod
    def _protect(value: str) -> str:
        raw = value.encode("utf-8")
        if os.name == "nt":
            import win32crypt  # type: ignore
            protected = win32crypt.CryptProtectData(raw, "XiaoZhiAssistant", None, None, None, 0)[1]
            return "dpapi:" + base64.b64encode(protected).decode("ascii")
        return "plain-b64:" + base64.b64encode(raw).decode("ascii")

    @staticmethod
    def _unprotect(value: str) -> str:
        if value.startswith("dpapi:"):
            import win32crypt  # type: ignore
            blob = base64.b64decode(value[6:])
            return win32crypt.CryptUnprotectData(blob, None, None, None, 0)[1].decode("utf-8")
        if value.startswith("plain-b64:"):
            return base64.b64decode(value[10:]).decode("utf-8")
        return ""

    def set(self, key: str, value: str) -> None:
        data = self._load()
        if value:
            data[key] = self._protect(value)
        else:
            data.pop(key, None)
        self._save(data)

    def get(self, key: str, default: str = "") -> str:
        raw = self._load().get(key)
        if not raw:
            return default
        try:
            return self._unprotect(raw)
        except Exception:
            return default

    def has(self, key: str) -> bool:
        return bool(self.get(key))
