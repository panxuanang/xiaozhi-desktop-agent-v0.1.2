# 小智打工人搭子 / 小智电脑助手

这是一个 Windows x64 的可安装 MVP 工程，目标是把已经验证过的链路收成一个用户可以直接安装和使用的桌面程序：

**普通微信 → WeixinChannel → Task Center → DeepSeek Router → Local / Direct DeepSeek / DeepSeek Harness → Task Center → 微信回传 / 桌面微信交付**

构建结果是一个可下载的 **`XiaoZhiSetup.exe`**。安装后不要求用户另外安装 Python、Node 或 OpenClaw Runtime；安装包自带私有 Python 3.12.10、DeepSeek Harness Python SDK/runtime、Office Python 库和 WeixinChannel 实现。

## 已包含的能力

- 微信 Claw / iLink 2.4.9：扫码登录、凭证恢复、长轮询、文字收发、文件收发。
- Task Center：SQLite 持久化 `task_id`、状态、输入/输出文件、版本、审批版本、SHA256、审核/交付联系人、定时字段等。
- DeepSeek Intent Router：先建任务，再分流到 Local / Direct / Harness。
- Local Driver：打开/关闭程序、打开 URL、截图、音量、找/复制/移动文件、常用简单 Excel 操作。
- Direct DeepSeek：通知、文案、润色、改写、总结、材料等一次调用任务。
- Harness Worker：复杂研究、复杂 Excel、Word/PPT、多步骤代码执行；输出按 `V1/V2/...` 保留，不覆盖旧版本。
- Office：构建时优先抓取 `@deepseek-ai/dsh-skill-office@0.1.6-alpha.2` 的官方 Office Skills；抓取失败时使用项目自带 fallback 指南。最终 Office 文件会被 Python 库重新打开验证。
- 审批与交付：`可以，这版发给王总` 会先锁定 `approved_version + approved_hash`，再把**那一版原文件**交给桌面微信 Driver，不会批准 V2 后又生成 V3。
- 桌面微信 Driver：用于向真实微信联系人发送文字/文件；Claw 只负责“我 ↔ 小智”。
- 本地 Web 控制台：只监听 `127.0.0.1`，用于首装配置、扫码、状态和任务查看。
- DeepSeek API Key 使用 Windows DPAPI 按当前 Windows 用户加密保存。

## 为什么安装包里仍然有很多文件，但你只下载一个 EXE

GitHub Actions 最终对外只产出一个 `XiaoZhiSetup.exe`。安装包内部会展开私有 Python Runtime、Harness Runtime、Office 库和应用源码。这比把整个系统硬塞成 PyInstaller `--onefile` 更稳定，也保留了 Harness 执行 Agent 自己生成 Python 脚本的能力。

## GitHub 上构建

如果你不熟悉 GitHub，直接按仓库里的 `GITHUB_BUILD.md` 操作。


1. 新建 GitHub 仓库，把本工程全部文件上传到仓库根目录。
2. 打开 **Actions → Build Windows Installer → Run workflow**。
3. 等待 Windows 构建完成。
4. 在该次 Workflow 的 Artifacts 下载 `XiaoZhiSetup-windows-x64`，里面只有 `XiaoZhiSetup.exe`。
5. 如果用 `v0.1.2` 这类 tag 推送，Workflow 还会把 `XiaoZhiSetup.exe` 直接放到 GitHub Release。

## 用户安装后的第一次使用

双击 `XiaoZhiSetup.exe` 安装。安装完成会启动“小智电脑助手”并打开浏览器里的本机控制台：

1. 点“选择”，选择一个 Harness 工作空间，例如 `D:\XiaoZhiWorkspace`。
2. 输入 DeepSeek API Key，默认模型 `deepseek-flash`，点“保存配置”和“测试 API”。
3. 点“连接微信”，页面出现二维码后用普通手机微信扫一扫并确认。
4. 微信状态变成“connected / 微信消息监听中”后，可以直接在手机微信 Claw 对话里发任务。

例如：

```text
把下载目录里的销售表整理一下，分析异常，做一份 PPT，做好先发我。
```

收到 V1 后：

```text
第二页简单一点。
```

收到 V2 后：

```text
可以，这版发给王总。
```

Task Center 会锁定 V2 的 SHA256，然后由桌面微信 Driver 发送 V2 原文件。

## Harness Windows 权限模式

当前工程固定安装 `deepseek-harness-sdk==0.1.5rc1`，因为截至 2026-09-20 这是 PyPI 当前发布的 0.1.5rc1 Python SDK，并且与你已经验证过的 Windows 环境一致。

默认流程：

1. 先使用完整 `sdk` profile + `DSH_PERMISSION_MODE=workspace-write`。
2. 如果命中 Windows SEA / workspace-write 已知执行链故障（典型 `error: --profile <name> is required`），且控制台勾选了兼容回退，则同一个完整 `sdk` profile 以 `DSH_PERMISSION_MODE=danger-full-access` 重试。

这样兼容回退仍保留 full SDK 的 Web/Skills/文件工具面，而不是切到工具更少的 `sdk-minimal`。

**danger-full-access 不是商业版安全隔离方案。** 本工程把它明确作为当前 Windows Harness 的个人 MVP 兼容路径。正式商业发布前应换成低权限 Worker / 独立受限用户 / 稳定的 Workspace Sandbox。

## 本地 Driver 范围

当前白名单包括：

- `open_app / close_app / window_control`
- `open_path / open_url`
- `screenshot`
- `volume_up / volume_down / volume_mute`
- `find_files / list_dir / make_dir / rename_path / copy_file / move_file`
- `excel_sort / excel_filter / excel_dedupe / excel_replace / excel_fill_blank / excel_sum`
- `excel_compute_column / excel_conditional_red / excel_conditional_set`
- `excel_merge_files / excel_lookup / excel_batch_replace`
- `excel_split_by_column / excel_split_sheets`
- `wechat_send_text / wechat_send_file`

复杂、不确定、需要自主规划的 Excel/Office/Research 会自动交给 Harness，而不是继续往 Local Driver 里塞任意 shell。

破坏性删除没有做成“模型随口一句就永久删除”的白名单动作；需要删除类能力时应先加入回收站/确认机制。

## 重要边界

### 1. 桌面微信 Driver 需要电脑端微信已登录

给“王总”等真实联系人交付，走的是桌面微信 UI 自动化。微信客户端 UI 版本变化可能需要调整 `drivers/wechat_desktop.py`；如果 UIA 看不到窗口，Driver 会明确失败，不会返回假成功。

### 2. Weixin/iLink 商业条款需要另行确认

本工程技术实现依据腾讯公开的 `Tencent/openclaw-weixin` 客户端协议路线。客户端仓库是 MIT，并不自动等于第三方商业软件对腾讯 iLink 后端拥有无限制商业接入权、SLA 或分发权。正式商业化前需要单独确认腾讯侧服务条款。

### 3. 这是“完整可安装 MVP”，不是已经完成全部商业安全工程

它已经把核心功能链、Task Center、版本审批、Harness、微信 Channel、本地 Driver、单 EXE 安装构建都放进同一个仓库，但仍建议在真实用户发布前补：

- Harness 低权限隔离与自动化安全测试；
- 桌面微信不同版本回归测试；
- iLink 8–24 小时在线/限流/商业权限长期测试；
- 代码签名与自动更新；
- 崩溃报告和诊断包；
- 更严格的联系人确认与高风险本地操作审批。

## 本地手工构建

在 Windows 机器上安装 Git、Node.js 22 和 Inno Setup 6 后，可在仓库根目录运行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
.\scripts\fetch_office_skills.ps1
.\scripts\stage_runtime.ps1
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" .\installer\xiaozhi.iss
```

输出：

```text
dist\XiaoZhiSetup.exe
```


## Build note

See `BUILD_FIXES_v0.1.2.md` for the embedded-Python path fix and the exact GitHub Actions verification gates.
