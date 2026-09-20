from __future__ import annotations

import logging
import re
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from .config import ConfigStore
from .deepseek_client import DeepSeekClient
from .drivers.local import LocalDriver
from .drivers.wechat_desktop import WeChatDesktopDriver
from .harness_worker import HarnessWorker
from .models import InboundMessage, RouteDecision, WorkResult
from .router import IntentRouter
from .secrets_store import SecretStore
from .task_center import TaskCenter
from .weixin import WeixinChannel

log = logging.getLogger(__name__)


def new_task_id() -> str:
    now = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"TASK-{now}-{secrets.token_hex(2).upper()}"


class TaskService:
    def __init__(
        self,
        center: TaskCenter,
        config_store: ConfigStore,
        secrets_store: SecretStore,
        channel: WeixinChannel,
    ):
        self.center = center
        self.config_store = config_store
        self.secrets = secrets_store
        self.channel = channel
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="xiaozhi-task")
        self.wechat_driver = WeChatDesktopDriver()

    def _send_self(self, msg: InboundMessage | dict, text: str) -> None:
        try:
            if isinstance(msg, InboundMessage):
                self.channel.send_text(msg.user_id, text, msg.context_token)
            else:
                self.channel.send_text(str(msg["channel_user_id"]), text, str(msg.get("context_token") or ""))
        except Exception:
            log.exception("Failed to send Weixin text")

    def handle_message(self, msg: InboundMessage) -> None:
        text = (msg.text or "").strip()
        if not text and not msg.attachments:
            return
        if self._handle_control_message(msg, text):
            return

        cfg = self.config_store.load()
        workspace = cfg.workspace_path
        api_key = self.secrets.get("deepseek_api_key")
        if not workspace or not api_key:
            self._send_self(msg, "小智还没配置完成。请先在电脑端打开小智设置，选择 Harness 工作空间并填写 DeepSeek API Key。")
            return

        task_id = new_task_id()
        self.center.create_task(
            task_id=task_id,
            workspace=str(workspace),
            channel=msg.channel,
            channel_user_id=msg.user_id,
            source_message_id=msg.message_id,
            context_token=msg.context_token,
            original_message=text,
            input_files=[str(p) for p in msg.attachments],
        )

        try:
            client = DeepSeekClient(api_key, cfg.deepseek_base_url, cfg.model)
            router = IntentRouter(client)
            decision = router.route(text or "处理我发来的文件", msg.attachments)
            # Persist all future-action semantics before telling the user they will happen.
            self.center.update_task(
                task_id,
                route=decision.route,
                route_summary=decision.summary,
                review_contact=decision.review_contact,
                delivery_contact=decision.delivery_contact,
                delivery_mode=decision.delivery_mode,
                completion_action=decision.completion_action,
                scheduled_at=decision.scheduled_at,
                current_stage="routed",
                latest_action=f"route:{decision.route}",
            )
        except Exception as exc:
            self.center.update_task(task_id, status="failed", error=str(exc), current_stage="router_failed")
            self._send_self(msg, f"{task_id} 创建成功，但任务分流失败：{exc}")
            return

        ack = f"已收到 {task_id}，正在处理。"
        if decision.delivery_mode == "on_complete" and decision.delivery_contact:
            ack = f"已收到 {task_id}。完成后会按当前任务记录直接发送给「{decision.delivery_contact}」。"
        elif decision.delivery_mode == "review":
            ack = f"已收到 {task_id}。完成后先发给你审核。"
        elif decision.scheduled_at and decision.delivery_contact:
            ack = f"已收到 {task_id}。任务已记录定时交付：{decision.scheduled_at}，联系人「{decision.delivery_contact}」。"
        self._send_self(msg, ack)
        self.pool.submit(self._execute_new_task, task_id, msg, decision)

    def _handle_control_message(self, msg: InboundMessage, text: str) -> bool:
        compact = re.sub(r"\s+", "", text)
        if re.match(r"^(状态|进度|status)(TASK[-\w]+)?$", compact, re.I):
            m = re.search(r"TASK[-\w]+", compact, re.I)
            task = self.center.get_task(m.group(0).upper()) if m else self.center.latest_for_user(msg.user_id)
            if not task:
                self._send_self(msg, "没有找到任务。")
            else:
                self._send_self(
                    msg,
                    f"{task['task_id']}\n状态: {task['status']}\n阶段: {task.get('current_stage') or '-'}\n版本: V{task.get('version') or 0}\n最后动作: {task.get('latest_action') or '-'}"
                    + (f"\n错误: {task['error']}" if task.get("error") else ""),
                )
            return True

        latest = self.center.latest_for_user(msg.user_id, ("awaiting_review", "completed"))
        if latest and self._is_approval(text):
            contact = self._extract_delivery_contact(text) or latest.get("delivery_contact")
            self.center.update_task(latest["task_id"], context_token=msg.context_token)
            self.pool.submit(self._approve_and_maybe_deliver, latest["task_id"], msg, contact)
            return True

        if latest and self._is_revision(text) and int(latest.get("version") or 0) > 0:
            self.center.update_task(
                latest["task_id"],
                status="running",
                context_token=msg.context_token,
                current_stage="revision_queued",
                latest_action="revision_requested",
                error=None,
            )
            self._send_self(msg, f"收到，继续修改 {latest['task_id']}，旧版本不会覆盖。")
            self.pool.submit(self._run_revision, latest["task_id"], msg)
            return True
        return False

    @staticmethod
    def _is_approval(text: str) -> bool:
        compact = re.sub(r"\s+", "", text)
        return (
            bool(re.search(r"^(可以|通过|就这版|这版可以|确认|批准)", compact))
            or "这版发" in compact
            or ("发给" in compact and "这版" in compact)
            or bool(re.search(r"最终(?:版|版本).*发(?:给)?", compact))
            or bool(re.search(r"(?:这个|当前)版本.*发(?:给)?", compact))
        )

    @staticmethod
    def _is_revision(text: str) -> bool:
        compact = re.sub(r"\s+", "", text)
        return bool(re.search(r"(第[一二三四五六七八九十0-9]+页|修改|改一下|改成|简单一点|再精简|再调整|换成|增加|删掉)", compact))

    @staticmethod
    def _extract_delivery_contact(text: str) -> str | None:
        compact = re.sub(r"\s+", "", text)
        m = re.search(r"发(?:给)?([^，。,.！!？?]{1,12})", compact)
        if not m:
            return None
        contact = m.group(1)
        contact = re.sub(r"(吧|。|！|!|，|,)$", "", contact)
        if contact in {"我", "我审核", "我看看"}:
            return None
        return contact

    def _execute_new_task(self, task_id: str, msg: InboundMessage, decision: RouteDecision) -> None:
        cfg = self.config_store.load()
        api_key = self.secrets.get("deepseek_api_key")
        try:
            self.center.update_task(task_id, status="running", current_stage=f"{decision.route}_running")
            if decision.route == "direct":
                result = self._run_direct(msg.text, api_key, cfg.deepseek_base_url, cfg.model)
                self._complete_text_task(task_id, msg, decision, result)
                return
            if decision.route == "local":
                result = self._run_local(msg.text, cfg, api_key)
                if not result.ok and result.error == "HANDOFF_HARNESS":
                    decision.route = "harness"
                    self.center.update_task(task_id, route="harness", route_summary="local planner handed off to harness")
                else:
                    self._complete_local_task(task_id, msg, decision, result)
                    return
            self._run_harness_new(task_id, msg, decision, cfg, api_key)
        except Exception as exc:
            log.exception("Task execution failed %s", task_id)
            self.center.update_task(task_id, status="failed", error=str(exc), current_stage="failed")
            self._send_self(msg, f"{task_id} 执行失败：{exc}")

    def _run_direct(self, text: str, api_key: str, base_url: str, model: str) -> WorkResult:
        client = DeepSeekClient(api_key, base_url, model)
        answer = client.chat(
            [
                {"role": "system", "content": "你是小智打工人搭子。直接完成用户的文字任务，输出可直接使用的中文结果。"},
                {"role": "user", "content": text},
            ],
            max_tokens=12_000,
        )
        return WorkResult(True, text=answer)

    def _run_local(self, text: str, cfg, api_key: str) -> WorkResult:
        workspace = cfg.workspace_path
        assert workspace is not None
        router = IntentRouter(DeepSeekClient(api_key, cfg.deepseek_base_url, cfg.model))
        action, args = router.plan_local(text, workspace)
        return LocalDriver(workspace).execute(action, args)

    def _complete_text_task(self, task_id: str, msg: InboundMessage, decision: RouteDecision, result: WorkResult) -> None:
        if not result.ok:
            raise RuntimeError(result.error or "Direct task failed")
        if decision.delivery_mode == "on_complete" and decision.delivery_contact:
            self.wechat_driver.send_text(decision.delivery_contact, result.text)
            self.center.record_delivery(task_id=task_id, version=0, contact=decision.delivery_contact, channel="desktop_wechat", status="sent", detail="text")
            self.center.update_task(task_id, status="completed", delivered_at=datetime.now(timezone.utc).isoformat(), latest_action="direct_text_delivered")
            self._send_self(msg, f"{task_id} 已完成并发送给「{decision.delivery_contact}」。")
        else:
            self.channel.send_text(msg.user_id, f"{task_id} 已完成：\n\n{result.text}", msg.context_token)
            self.center.update_task(task_id, status="completed", current_stage="completed", latest_action="direct_reply_sent")

    def _complete_local_task(self, task_id: str, msg: InboundMessage, decision: RouteDecision, result: WorkResult) -> None:
        if not result.ok:
            raise RuntimeError(result.error or "Local task failed")
        if result.files:
            version, _ = self.center.add_version(task_id, result.files)
            if decision.delivery_mode == "on_complete" and decision.delivery_contact:
                self.center.approve_version(task_id, version)
                approved = self.center.verified_approved_version(task_id)
                exact = [Path(row["path"]) for row in approved["files"]]
                self.wechat_driver.send_files(decision.delivery_contact, exact)
                self.center.record_delivery(task_id=task_id, version=version, contact=decision.delivery_contact, channel="desktop_wechat", status="sent", detail=approved["hash"])
                self.center.update_task(task_id, status="completed", delivered_at=datetime.now(timezone.utc).isoformat(), latest_action="local_files_delivered")
                self._send_self(msg, f"{task_id} 已完成，并把 V{version} 原文件发送给「{decision.delivery_contact}」。")
            else:
                version_row = self.center.get_version(task_id, version) or {"files": []}
                review_files = [Path(row["path"]) for row in version_row["files"]]
                self.channel.send_text(msg.user_id, f"{task_id} 已完成，生成 V{version}。", msg.context_token)
                for p in review_files:
                    self.channel.send_file(msg.user_id, p, msg.context_token)
                self.center.update_task(task_id, status="awaiting_review", current_stage="awaiting_review", latest_action="local_files_sent_for_review")
        else:
            self.channel.send_text(msg.user_id, f"{task_id} 已完成：{result.text}", msg.context_token)
            self.center.update_task(task_id, status="completed", current_stage="completed", latest_action="local_done")

    def _run_harness_new(self, task_id: str, msg: InboundMessage, decision: RouteDecision, cfg, api_key: str) -> None:
        task = self.center.get_task(task_id) or {}
        worker = HarnessWorker(cfg, api_key)
        self.center.update_task(task_id, current_stage="harness_running", latest_action="harness_started")
        result = worker.run_task(
            task_id=task_id,
            text=msg.text or "处理用户发来的文件并完成任务",
            input_files=msg.attachments,
            next_version=1,
            session_id=str(task.get("harness_session_id") or f"xiaozhi-{task_id}"),
            on_event=lambda e: self.center.update_task(task_id, latest_action=f"harness:{e}"),
        )
        self._finish_harness(task_id, msg, decision, result)

    def _run_revision(self, task_id: str, msg: InboundMessage) -> None:
        cfg = self.config_store.load()
        api_key = self.secrets.get("deepseek_api_key")
        task = self.center.get_task(task_id)
        if not task:
            return
        worker = HarnessWorker(cfg, api_key)
        next_version = int(task.get("version") or 0) + 1
        previous = [Path(p) for p in task.get("output_files") or []]
        inputs = [Path(p) for p in task.get("input_files") or []]
        revision_session_id = f"xiaozhi-{task_id}-v{next_version}-{secrets.token_hex(3)}"
        # Use a fresh Harness runtime/session for each revision. Previous output
        # files are explicitly supplied in the prompt, so version continuity does
        # not depend on fragile cross-process session resume semantics.
        self.center.update_task(task_id, harness_session_id=revision_session_id)
        result = worker.run_task(
            task_id=task_id,
            text=f"这是对现有成果的修改要求：{msg.text}",
            input_files=inputs,
            next_version=next_version,
            session_id=revision_session_id,
            revision_of=previous,
            on_event=lambda e: self.center.update_task(task_id, latest_action=f"harness_revision:{e}"),
        )
        decision = RouteDecision(route="harness", summary="revision", delivery_mode="review", completion_action="send", review_contact="我")
        self._finish_harness(task_id, msg, decision, result)

    def _finish_harness(self, task_id: str, msg: InboundMessage, decision: RouteDecision, result: WorkResult) -> None:
        if not result.ok:
            self.center.update_task(task_id, status="failed", error=result.error, current_stage="harness_failed")
            self._send_self(msg, f"{task_id} Harness 执行失败：{result.error}")
            return
        if not result.files:
            self.center.update_task(task_id, status="completed", current_stage="completed", latest_action="harness_text_completed")
            self.channel.send_text(msg.user_id, f"{task_id} 已完成：\n\n{result.text or '任务完成'}", msg.context_token)
            return

        version, digest = self.center.add_version(task_id, result.files)
        mode = result.metadata.get("harness_mode")
        self.center.update_task(task_id, current_stage="outputs_verified", latest_action=f"v{version}_verified_{mode}")

        if decision.delivery_mode == "on_complete" and decision.delivery_contact:
            self.center.approve_version(task_id, version)
            approved = self.center.verified_approved_version(task_id)
            exact = [Path(row["path"]) for row in approved["files"]]
            self.wechat_driver.send_text(decision.delivery_contact, f"小智任务 {task_id} 已完成，发送最终文件 V{version}。")
            self.wechat_driver.send_files(decision.delivery_contact, exact)
            self.center.record_delivery(task_id=task_id, version=version, contact=decision.delivery_contact, channel="desktop_wechat", status="sent", detail=approved["hash"])
            self.center.update_task(task_id, status="completed", delivered_at=datetime.now(timezone.utc).isoformat(), latest_action=f"v{version}_delivered")
            self._send_self(msg, f"{task_id} 已完成并发送 V{version} 给「{decision.delivery_contact}」。SHA256 批次指纹：{digest[:16]}…")
            return

        if decision.delivery_mode == "scheduled" and decision.delivery_contact and decision.scheduled_at:
            self.center.approve_version(task_id, version)
            self.center.update_task(task_id, status="completed", latest_action=f"v{version}_waiting_scheduled_delivery")
            self._send_self(msg, f"{task_id} 已完成 V{version}，将按任务记录在 {decision.scheduled_at} 发送给「{decision.delivery_contact}」。")
            return

        version_row = self.center.get_version(task_id, version) or {"files": []}
        review_files = [Path(row["path"]) for row in version_row["files"]]
        self.channel.send_text(msg.user_id, f"{task_id} 已完成 V{version}，先发给你审核。\n{result.text[:1500]}", msg.context_token)
        for p in review_files:
            self.channel.send_file(msg.user_id, p, msg.context_token)
        self.center.update_task(task_id, status="awaiting_review", current_stage="awaiting_review", latest_action=f"v{version}_sent_for_review")

    def _approve_and_maybe_deliver(self, task_id: str, msg: InboundMessage, contact: str | None) -> None:
        try:
            self.center.approve_version(task_id)
            approved = self.center.verified_approved_version(task_id)
            version = approved["version"]
            if not contact:
                self.center.update_task(task_id, status="completed", latest_action=f"v{version}_approved")
                self._send_self(msg, f"{task_id} 的 V{version} 已批准。已锁定 SHA256 批次指纹 {approved['hash'][:16]}…")
                return
            # Persist destination before making the delivery promise.
            self.center.update_task(task_id, delivery_contact=contact, completion_action="send", delivery_mode="approved_send")
            exact = [Path(row["path"]) for row in approved["files"]]
            self.wechat_driver.send_text(contact, f"小智任务 {task_id} 最终版本 V{version}。")
            self.wechat_driver.send_files(contact, exact)
            self.center.record_delivery(task_id=task_id, version=version, contact=contact, channel="desktop_wechat", status="sent", detail=approved["hash"])
            self.center.update_task(task_id, status="completed", delivered_at=datetime.now(timezone.utc).isoformat(), latest_action=f"approved_v{version}_delivered")
            self._send_self(msg, f"已把你批准的 V{version} 原文件发送给「{contact}」，没有重新生成。")
        except Exception as exc:
            log.exception("Approval/delivery failed")
            self.center.update_task(task_id, status="failed", error=str(exc), latest_action="delivery_failed")
            self._send_self(msg, f"{task_id} 审批/发送失败：{exc}")

    def run_due_deliveries(self) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for task in self.center.scheduled_ready(now):
            try:
                version = int(task.get("approved_version") or 0)
                if version <= 0:
                    continue
                approved = self.center.verified_approved_version(task["task_id"])
                contact = str(task.get("delivery_contact") or "")
                if not contact:
                    continue
                files = [Path(row["path"]) for row in approved["files"]]
                self.wechat_driver.send_files(contact, files)
                self.center.record_delivery(task_id=task["task_id"], version=version, contact=contact, channel="desktop_wechat", status="sent", detail="scheduled")
                self.center.update_task(task["task_id"], delivered_at=now, latest_action=f"scheduled_v{version}_delivered")
                self._send_self(task, f"{task['task_id']} 已按计划把 V{version} 发送给「{contact}」。")
            except Exception as exc:
                log.exception("Scheduled delivery failed")
                self.center.update_task(task["task_id"], error=str(exc), latest_action="scheduled_delivery_failed")
