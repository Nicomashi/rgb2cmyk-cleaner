# 开发

[Русский](development.md) · [English](development.en.md) · [简体中文](development.zh-CN.md)

通过 `uv sync --locked` 安装 Python 依赖。运行应用和集成测试需要在 `profiles/source-fogra39.icc` 放置 CMYK ICC 色彩配置文件；测试预期结果以 FOGRA39 为基准。

## 检查

```sh
uv run python -B -m pytest -q -p no:cacheprovider
node --test tests/*.test.mjs
node --check frontend/workspace.js
```

测试涵盖通道清理、ICC 转换、取样点、TIFF 导出、取消处理、会话清理、翻译和语言记忆。测试文件在独立目录中创建。

## 构建界面

修改 `frontend/` 后，请重新构建 `static/ui.js`，并将构建结果纳入提交：

```sh
npm ci
npm run build
```

## 项目结构

- `app.py`：API 和工作会话管理。
- `cleaner/`：色彩转换、清理算法和导出。
- `frontend/`：界面源代码。
- `frontend/locales.js`：俄语、英语和中文界面翻译。
- `static/`：提供给浏览器的文件。
- `tests/`：Python 和 JavaScript 测试。
- `service.py`：macOS 自动启动管理。

上传文件和导出结果临时保存在 `.runtime/`，预览图保存在内存中。打开新文件、刷新页面或重启服务器会清空工作数据。`.runtime/` 和 `profiles/` 目录不纳入 Git。
