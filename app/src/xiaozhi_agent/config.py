from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from .paths import CONFIG_FILE


@dataclass(slots=True)
class AppConfig:
    workspace: str = ""
    model: str = "deepseek-flash"
    deepseek_base_url: str = "https://api.deepseek.com"
    harness_safe_mode: bool = True
    allow_harness_full_access_fallback: bool = True
    auto_start_weixin: bool = True
    auto_start_windows: bool = False
    web_port: int = 8765
    max_workers: int = 2
    last_updated: str = ""

    @property
    def workspace_path(self) -> Path | None:
        if not self.workspace:
            return None
        return Path(os.path.expandvars(os.path.expanduser(self.workspace))).resolve()


class ConfigStore:
    def __init__(self, path: Path = CONFIG_FILE):
        self.path = path

    def load(self) -> AppConfig:
        if not self.path.exists():
            return AppConfig()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            allowed = {f.name for f in fields(AppConfig)}
            return AppConfig(**{k: v for k, v in data.items() if k in allowed})
        except Exception:
            return AppConfig()

    def save(self, config: AppConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def update(self, **patch: Any) -> AppConfig:
        cfg = self.load()
        allowed = {f.name for f in fields(AppConfig)}
        for key, value in patch.items():
            if key in allowed:
                setattr(cfg, key, value)
        self.save(cfg)
        return cfg
