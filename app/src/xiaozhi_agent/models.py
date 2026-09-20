from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class InboundMessage:
    channel: str
    user_id: str
    message_id: str
    message_type: str
    text: str
    attachments: list[Path] = field(default_factory=list)
    context_token: str = ""
    received_at: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RouteDecision:
    route: str
    summary: str = ""
    local_action: str | None = None
    local_args: dict[str, Any] = field(default_factory=dict)
    review_contact: str | None = None
    delivery_contact: str | None = None
    delivery_mode: str | None = None
    completion_action: str | None = None
    scheduled_at: str | None = None
    reason: str = ""


@dataclass(slots=True)
class WorkResult:
    ok: bool
    text: str = ""
    files: list[Path] = field(default_factory=list)
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
