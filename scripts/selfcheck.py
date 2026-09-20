from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "app" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from xiaozhi_agent.router import IntentRouter
from xiaozhi_agent.task_center import TaskCenter
from xiaozhi_agent.weixin.channel import OFFICIAL_PLUGIN_VERSION, version_number


class NoNetworkClient:
    def json_chat(self, *_args, **_kwargs):
        raise AssertionError("heuristic route unexpectedly called network")


def check_task_center() -> None:
    # On Windows, an open sqlite3 connection keeps tasks.db locked.  Always close
    # TaskCenter *before* TemporaryDirectory tries to remove the directory.
    with tempfile.TemporaryDirectory(prefix="xiaozhi-selfcheck-", ignore_cleanup_errors=True) as td:
        root = Path(td)
        center = TaskCenter(root / "tasks.db")
        try:
            center.create_task(
                task_id="TASK-TEST", workspace=str(root), channel="weixin", channel_user_id="u1",
                source_message_id="m1", context_token="ctx", original_message="test", input_files=[]
            )
            out = root / "a.txt"
            out.write_text("hello", encoding="utf-8")
            version, digest = center.add_version("TASK-TEST", [out])
            assert version == 1 and len(digest) == 64
            approved = center.approve_version("TASK-TEST")
            assert approved["version"] == 1 and approved["hash"] == digest
            verified = center.verified_approved_version("TASK-TEST")
            assert verified["version"] == 1 and verified["hash"] == digest
        finally:
            center.close()


def check_router() -> None:
    router = IntentRouter(NoNetworkClient())
    assert router.route("打开微信", []).route == "local"
    assert router.plan_local("打开微信", Path(".")) == ("open_app", {"name": "微信"})
    assert router.plan_local("关闭 Excel", Path(".")) == ("close_app", {"name": "excel"})
    assert router.route("研究这个行业，做一份 PPT", []).route == "harness"
    assert router.route("帮我写一份通知", []).route == "direct"


def main() -> int:
    check_task_center()
    check_router()
    assert OFFICIAL_PLUGIN_VERSION == "2.4.9"
    assert version_number("2.4.9") == 132105
    print("SELF_CHECK_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
