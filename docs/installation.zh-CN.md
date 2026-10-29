# 安装：Windows、Linux 和 macOS

[Русский](installation.md) · [English](installation.en.md) · [简体中文](installation.zh-CN.md)

你可以把仓库链接交给 AI 助手，请它完成安装。若要手动安装，请先按照对应系统的说明准备 Git 和 uv，再执行下方的通用步骤。

本指南适用于 Windows x64、使用 glibc 2.28+ 的 Linux x64，以及搭载 Apple Silicon 的 macOS 14+。当前依赖在这些平台上提供预编译安装包。

## Windows

打开 PowerShell。如果尚未安装 Git 和 uv，请执行：

```powershell
winget install --id Git.Git -e --source winget
winget install --id astral-sh.uv -e --source winget
```

关闭并重新打开 PowerShell，后续命令均在其中执行。

如果无法使用 WinGet，请使用 [Git for Windows 安装程序](https://git-scm.com/install/windows)和 [uv 的其他安装方式](https://docs.astral.sh/uv/getting-started/installation/)。

## Linux

通过包管理器安装 Git 和 curl。Ubuntu 和 Debian 用户可执行：

```sh
sudo apt-get update
sudo apt-get install git curl
```

其他发行版请参阅 [Git 安装指南](https://git-scm.com/install/linux)。

安装 uv：

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

关闭并重新打开终端。

## macOS

打开“终端”。如果尚未安装 Git，请安装 Apple 命令行工具并等待安装完成：

```sh
xcode-select --install
```

安装 uv：

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

关闭并重新打开“终端”。如果使用 Homebrew，也可以执行 `brew install git uv`，代替上面的两项安装命令。

安装方式：[Git for macOS](https://git-scm.com/install/mac)、[uv](https://docs.astral.sh/uv/getting-started/installation/)。

## 所有系统通用的步骤

选择存放应用的文件夹，并在该文件夹中打开终端。以下命令适用于 PowerShell、Linux 和 macOS：

```sh
git clone https://github.com/Nicomashi/rgb2cmyk-cleaner.git
cd rgb2cmyk-cleaner
uv sync --locked --python 3.13
```

uv 会在项目环境中准备 Python 和依赖。

### 添加印刷色彩配置文件

在项目文件夹内创建 `profiles` 文件夹，将 CMYK ICC 色彩配置文件放入其中，并命名为 `source-fogra39.icc`。

项目不附带该配置文件。你可以向印刷服务商索取与实际印刷条件匹配的配置文件。应用要求使用上述文件名；重命名不会改变配置文件的内容。

### 启动应用

在项目文件夹中执行：

```sh
uv run python -B -m uvicorn app:app --host 127.0.0.1 --port 8765
```

在浏览器中打开 **http://127.0.0.1:8765**。点击“示例”，尝试调整清理参数并下载 TIFF。

使用期间请保持终端打开。按 **Ctrl+C** 停止应用。下次使用时，在项目文件夹中打开终端，再次执行最后一条命令即可。

## 可选：自动启动

日常使用不需要配置自动启动。如果希望登录系统后自动运行应用，可以请 AI 助手按对应系统设置：

- **Windows：**使用任务计划程序。
- **Linux：**如果发行版支持，使用 systemd 用户服务。
- **macOS：**使用项目附带的 `service.py`。

在 Windows 和 Linux 上，请让助手从项目文件夹运行 `uv run --offline --no-sync python -B -m uvicorn app:app --host 127.0.0.1 --port 8765`，指定 uv 的完整路径，并启用故障后重新启动。

在 macOS 上，先停止手动启动的服务器，再执行：

```sh
uv run python -B service.py install
```

该命令会启用登录时自动启动和崩溃后自动恢复。若要关闭，请执行 `uv run python -B service.py uninstall`。`service.py` 和 `start.command` 仅适用于 macOS；Windows 和 Linux 使用前面的启动命令。
