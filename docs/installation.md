# Установка: Windows, Linux и macOS

Можно передать ссылку на этот репозиторий своему ИИ-агенту и попросить установить приложение. Для самостоятельной установки сначала подготовьте Git и uv по инструкции для своей системы, затем переходите к общим шагам.

Эта инструкция рассчитана на Windows x64, Linux x64 с glibc 2.28+ и macOS 14+ на Apple Silicon — для них доступны готовые пакеты текущего набора зависимостей.

## Windows

Откройте PowerShell и установите Git и uv, если их ещё нет:

```powershell
winget install --id Git.Git -e --source winget
winget install --id astral-sh.uv -e --source winget
```

Закройте и снова откройте PowerShell. Дальнейшие команды выполняйте в нём.

Если WinGet недоступен: [установщик Git для Windows](https://git-scm.com/install/windows) и [другие способы установки uv](https://docs.astral.sh/uv/getting-started/installation/).

## Linux

Установите Git и curl через пакетный менеджер. Для Ubuntu и Debian:

```sh
sudo apt-get update
sudo apt-get install git curl
```

Для других дистрибутивов — [инструкция установки Git](https://git-scm.com/install/linux).

Установите uv:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Закройте и снова откройте терминал.

## macOS

Откройте Terminal. Если Git ещё не установлен, установите инструменты командной строки Apple и дождитесь завершения установки:

```sh
xcode-select --install
```

Установите uv:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Закройте и снова откройте Terminal. Если пользуетесь Homebrew, вместо этих двух установок можно выполнить `brew install git uv`.

Способы установки: [Git для macOS](https://git-scm.com/install/mac), [uv](https://docs.astral.sh/uv/getting-started/installation/).

## Общие шаги для всех систем

Выберите папку, в которой хотите хранить приложение, и откройте в ней терминал. Следующие команды одинаковы для PowerShell, Linux и macOS:

```sh
git clone https://github.com/Nicomashi/rgb2cmyk-cleaner.git
cd rgb2cmyk-cleaner
uv sync --locked --python 3.13
```

uv подготовит Python и зависимости в окружении проекта.

### Подключите печатный профиль

Создайте в папке проекта каталог `profiles`. Поместите в него CMYK ICC-профиль под именем `source-fogra39.icc`.

Профиль не входит в комплект. Его можно получить у типографии: он должен соответствовать условиям печати. Имя файла нужно приложению; оно не меняет содержимое выбранного профиля.

### Запустите приложение

Из папки проекта:

```sh
uv run python -B -m uvicorn app:app --host 127.0.0.1 --port 8765
```

Откройте **http://127.0.0.1:8765** в браузере. Нажмите «Демо», попробуйте очистку и скачайте TIFF.

Оставьте терминал открытым на время работы. Для остановки нажмите **Ctrl+C**. При следующем запуске достаточно открыть терминал в папке проекта и повторить последнюю команду.

## Автозапуск — по желанию

Для обычной работы он не нужен. Если хотите запускать приложение при входе в систему, поручите агенту настроить автозапуск для вашей ОС:

- **Windows:** через Планировщик заданий.
- **Linux:** через пользовательскую службу systemd, если она доступна в дистрибутиве.
- **macOS:** через готовый `service.py` из проекта.

На Windows и Linux агенту нужно настроить запуск из папки проекта командой `uv run --offline --no-sync python -B -m uvicorn app:app --host 127.0.0.1 --port 8765`, указать полный путь к uv и включить повторный запуск при сбое.

На macOS остановите ручной сервер и выполните:

```sh
uv run python -B service.py install
```

Эта команда включает запуск при входе в систему и восстановление после падения. Отключить: `uv run python -B service.py uninstall`. Файлы `service.py` и `start.command` предназначены только для macOS; на Windows и Linux используется команда запуска выше.
