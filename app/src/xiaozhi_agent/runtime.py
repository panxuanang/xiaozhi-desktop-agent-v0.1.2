from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from .config import AppConfig, ConfigStore
from .deepseek_client import DeepSeekClient
from .harness_worker import HarnessWorker
from .logging_setup import setup_logging
from .paths import LOG_DIR
from .secrets_store import SecretStore
from .task_center import TaskCenter
from .task_service import TaskService
from .weixin import WeixinChannel

log = logging.getLogger(__name__)


class XiaoZhiRuntime:
    def __init__(self):
        setup_logging()
        self.config_store = ConfigStore()
        self.secrets = SecretStore()
        self.center = TaskCenter()
        self.channel = WeixinChannel(self.secrets)
        self.task_service = TaskService(self.center, self.config_store, self.secrets, self.channel)
        self.channel.on_message = self.task_service.handle_message
        self.stop_event = threading.Event()
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True, name="xiaozhi-scheduler")
        self.scheduler_thread.start()
        cfg = self.config_store.load()
        if cfg.auto_start_weixin and self.channel.has_credentials():
            self.channel.start_polling()

    def _scheduler_loop(self) -> None:
        while not self.stop_event.wait(30):
            try:
                self.task_service.run_due_deliveries()
            except Exception:
                log.exception("Scheduler tick failed")

    def shutdown(self) -> None:
        self.stop_event.set()
        self.channel.stop()
        if self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=2.0)
        self.center.close()

    def status(self) -> dict[str, Any]:
        cfg = self.config_store.load()
        tasks = self.center.list_tasks(10)
        for task in tasks:
            task.pop("context_token", None)
        return {
            "configured": bool(cfg.workspace and self.secrets.has("deepseek_api_key")),
            "workspace": cfg.workspace,
            "model": cfg.model,
            "deepseek_api_configured": self.secrets.has("deepseek_api_key"),
            "harness_safe_mode": cfg.harness_safe_mode,
            "allow_harness_full_access_fallback": cfg.allow_harness_full_access_fallback,
            "weixin": self.channel.get_status(),
            "weixin_has_credentials": self.channel.has_credentials(),
            "tasks": tasks,
        }

    def save_config(self, data: dict[str, Any]) -> AppConfig:
        cfg = self.config_store.load()
        workspace = str(data.get("workspace") or cfg.workspace).strip()
        if workspace:
            p = Path(os.path.expandvars(os.path.expanduser(workspace))).resolve()
            p.mkdir(parents=True, exist_ok=True)
            workspace = str(p)
        cfg.workspace = workspace
        cfg.model = str(data.get("model") or cfg.model or "deepseek-flash").strip()
        cfg.deepseek_base_url = str(data.get("deepseek_base_url") or cfg.deepseek_base_url or "https://api.deepseek.com").strip().rstrip("/")
        if "harness_safe_mode" in data:
            cfg.harness_safe_mode = bool(data["harness_safe_mode"])
        if "allow_harness_full_access_fallback" in data:
            cfg.allow_harness_full_access_fallback = bool(data["allow_harness_full_access_fallback"])
        if "auto_start_weixin" in data:
            cfg.auto_start_weixin = bool(data["auto_start_weixin"])
        from datetime import datetime, timezone
        cfg.last_updated = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.config_store.save(cfg)
        api_key = str(data.get("api_key") or "").strip()
        if api_key:
            self.secrets.set("deepseek_api_key", api_key)
        if cfg.workspace and self.secrets.has("deepseek_api_key"):
            try:
                HarnessWorker(cfg, self.secrets.get("deepseek_api_key")).deploy_workspace_support()
            except Exception:
                log.exception("Deploying workspace support failed")
        return cfg

    def test_api(self) -> str:
        cfg = self.config_store.load()
        key = self.secrets.get("deepseek_api_key")
        return DeepSeekClient(key, cfg.deepseek_base_url, cfg.model).test()

    def start_weixin_login(self, force: bool = False) -> None:
        self.channel.start_login(force=force)

    def submit_weixin_verify(self, code: str) -> None:
        self.channel.submit_verify_code(code)

    def browse_workspace(self) -> str:
        if os.name != "nt":
            return ""
        try:
            import win32com.client  # type: ignore
            shell = win32com.client.Dispatch("Shell.Application")
            folder = shell.BrowseForFolder(0, "选择 Harness 工作空间", 0, 0)
            if folder is None:
                return ""
            return str(folder.Self.Path)
        except Exception:
            log.exception("BrowseForFolder failed")
            return ""

    def open_workspace(self) -> None:
        cfg = self.config_store.load()
        if cfg.workspace:
            os.startfile(cfg.workspace)  # type: ignore[attr-defined]

    def open_logs(self) -> None:
        os.startfile(str(LOG_DIR))  # type: ignore[attr-defined]
