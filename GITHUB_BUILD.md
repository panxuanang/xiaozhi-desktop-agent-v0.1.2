# 从源码到一个 XiaoZhiSetup.exe

这份工程已经配置 GitHub Actions。目标不是让最终用户安装 Python，而是让 GitHub 的 Windows 构建机把所有运行时打进一个安装器。

## 最简单的构建方法

1. 在 GitHub 新建一个空仓库，例如 `xiaozhi-desktop-agent`。
2. 把本工程 ZIP 解压后的**所有文件和目录**上传到仓库根目录，必须保留 `.github/workflows/build-windows.yml`。
3. 打开仓库顶部 **Actions**。
4. 左侧选择 **Build Windows Installer**。
5. 点 **Run workflow**。
6. 等构建完成后，进入该次运行，在 **Artifacts** 下载 `XiaoZhiSetup-windows-x64`。
7. GitHub 下载的是一个 Artifact ZIP，解压后里面的最终交付物只有：

   `XiaoZhiSetup.exe`

如果希望 GitHub Release 页面直接出现 EXE，可创建并推送类似 `v0.1.2` 的 tag；工作流会自动把 `XiaoZhiSetup.exe` 附到 Release。


## v0.1.2 构建自检

这版同时保留并修复了前两次 GitHub Windows 构建暴露的问题：

- `tasks.db / WinError 32`：self-check 会在临时目录清理前显式关闭 SQLite。
- `ModuleNotFoundError: xiaozhi_agent`：Python embeddable 的 `python312._pth` 会忽略 `PYTHONPATH`，所以现在把 `..\app\src` 直接写入 `python312._pth`，构建和安装后验证都不再依赖 `PYTHONPATH`。

工作流不会只看“编译成功”就上传安装包。成功构建必须依次看到：

```text
EMBEDDED_APP_PATH_OK
RUNTIME_IMPORTS_OK
SELF_CHECK_OK
STAGE_RUNTIME_OK
INSTALLED_APP_PATH_OK
INSTALLED_RUNTIME_IMPORTS_OK
SELF_CHECK_OK
INSTALLER_SMOKE_OK
```

最后三项来自对刚生成的 `XiaoZhiSetup.exe` 的静默安装烟雾测试。也就是说，GitHub 会先实际安装一次生成的 EXE、再用安装后的私有 Python 检查依赖与 Task Center，全部通过以后才上传 Artifact。

## 安装后的首次配置

双击 `XiaoZhiSetup.exe`：

1. 选择 Harness 工作空间。
2. 输入 DeepSeek API Key。
3. 默认模型保持 `deepseek-flash`。
4. 保存配置并测试 API。
5. 点击连接微信，用普通微信扫码。
6. 微信连接成功后即可直接从手机给小智发任务。

## 构建失败时看哪里

Actions 中最重要的步骤是：

- `Fetch official Office Skills when available`
- `Stage private Python runtime and dependencies`
- `Build single installer EXE`

第二步会执行源码编译、关键依赖导入以及 `SELF_CHECK_OK` 自检。任何一项失败都会让 GitHub 构建直接失败，而不是产出一个表面成功、实际缺依赖的安装器。

## Windows / Harness 当前兼容边界

项目固定 `deepseek-harness-sdk==0.1.5rc1`。默认先尝试 `workspace-write`；若命中当前 Windows runtime 已知的 sandbox 执行链问题，并且控制台启用了兼容回退，才会重试 `danger-full-access`。

`danger-full-access` 只适合当前个人 MVP/诊断阶段，不应直接作为多人商业发布的安全模型。
