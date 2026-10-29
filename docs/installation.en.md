# Installation: Windows, Linux, and macOS

[Русский](installation.md) · [English](installation.en.md) · [简体中文](installation.zh-CN.md)

You can give your AI agent the repository URL and ask it to install the app. To install it yourself, first set up Git and uv for your system, then follow the shared steps below.

This guide targets Windows x64, Linux x64 with glibc 2.28+, and macOS 14+ on Apple Silicon. Prebuilt packages for the current dependencies are available for these platforms.

## Windows

Open PowerShell and install Git and uv if needed:

```powershell
winget install --id Git.Git -e --source winget
winget install --id astral-sh.uv -e --source winget
```

Close and reopen PowerShell. Run the remaining commands there.

If WinGet is unavailable, use the [Git for Windows installer](https://git-scm.com/install/windows) and [other uv installation methods](https://docs.astral.sh/uv/getting-started/installation/).

## Linux

Install Git and curl with your package manager. On Ubuntu and Debian:

```sh
sudo apt-get update
sudo apt-get install git curl
```

For other distributions, see the [Git installation guide](https://git-scm.com/install/linux).

Install uv:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Close and reopen your terminal.

## macOS

Open Terminal. If Git is not installed, install Apple's command-line tools and wait for installation to finish:

```sh
xcode-select --install
```

Install uv:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Close and reopen Terminal. If you use Homebrew, you can run `brew install git uv` instead of the two installation commands above.

Installation options: [Git for macOS](https://git-scm.com/install/mac), [uv](https://docs.astral.sh/uv/getting-started/installation/).

## Shared steps for all systems

Choose a folder for the app and open a terminal there. These commands work in PowerShell, Linux, and macOS:

```sh
git clone https://github.com/Nicomashi/rgb2cmyk-cleaner.git
cd rgb2cmyk-cleaner
uv sync --locked --python 3.13
```

uv prepares Python and dependencies in the project's environment.

### Add a print profile

Create a `profiles` folder inside the project. Place a CMYK ICC profile there and name it `source-fogra39.icc`.

The profile is not included. Ask your print provider for a profile that matches the printing conditions. The filename is required by the app; renaming the file does not change the profile itself.

### Start the app

From the project folder:

```sh
uv run python -B -m uvicorn app:app --host 127.0.0.1 --port 8765
```

Open **http://127.0.0.1:8765** in your browser. Click **Demo**, try the cleanup controls, and download a TIFF.

Keep the terminal open while using the app. Press **Ctrl+C** to stop it. Next time, open a terminal in the project folder and repeat the last command.

## Optional automatic startup

Automatic startup is not required. If you want the app to start when you sign in, ask your agent to configure it for your system:

- **Windows:** use Task Scheduler.
- **Linux:** use a user systemd service, if available in your distribution.
- **macOS:** use the included `service.py`.

On Windows and Linux, have the agent run `uv run --offline --no-sync python -B -m uvicorn app:app --host 127.0.0.1 --port 8765` from the project folder, use the full path to uv, and enable restarting after failure.

On macOS, stop the manually started server and run:

```sh
uv run python -B service.py install
```

This enables startup at sign-in and recovery after a crash. To disable it, run `uv run python -B service.py uninstall`. The `service.py` and `start.command` files are for macOS only; Windows and Linux use the startup command above.
