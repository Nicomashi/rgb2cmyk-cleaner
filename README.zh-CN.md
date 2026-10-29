# RGB2CMYK Cleaner

[Русский](README.md) · [English](README.en.md) · [简体中文](README.zh-CN.md)

**最简单的安装方式：交给你的 AI 助手。** 将下面的请求复制给它：

> 请从 https://github.com/Nicomashi/rgb2cmyk-cleaner 在我的电脑上安装并启动 RGB2CMYK Cleaner。识别我的操作系统，按照仓库中的安装说明，通过 uv 安装依赖，并帮助我添加 CMYK ICC 色彩配置文件。确认示例图片可以打开、TIFF 可以导出后，给我应用的访问地址。

支持 **Windows、Linux 和 macOS**。[手动安装指南](docs/installation.zh-CN.md)。

快速为 AI 生成的图片做好印刷准备，让颜色更干净，无需复杂的手动调色。

最适合插画、海报和以纯色填充为主的图形。对人物照片的适用性较低：清理可能明显改变肤色。

![CMYK Clean：清理前后对比、参数设置和颜色取样点](docs/images/cmyk-clean-preview.png)

## 工作原理

应用使用印刷 ICC 色彩配置文件将图像转换为 CMYK，减少混入的多余彩色油墨，并用黑墨进行补偿。你可以调整清理强度和黑版补偿，同时对比原图与处理结果。

1. 打开图片，或点击“示例”试用。
2. 调整“清理强度”和“黑版补偿”，拖动分界线查看处理前后的差异。
3. 点击“下载 TIFF”，获得保持原始分辨率、嵌入 ICC 色彩配置文件的 CMYK 文件。

编辑时使用缩小的预览图，导出时处理原图。屏幕预览用于帮助选择参数；正式批量印刷前，建议先打样。

## 安装与启动

选择你的系统：[Windows](docs/installation.zh-CN.md#windows)、[Linux](docs/installation.zh-CN.md#linux) 或 [macOS](docs/installation.zh-CN.md#macos)。

在这三种系统上，应用均在本地运行，通过浏览器访问 **http://127.0.0.1:8765**。界面已构建完成，无需安装 Node.js。

## 操作方式

- **鼠标滚轮**：缩放；**空格 + 拖动**：平移图像。
- **移动鼠标**：查看光标位置的 CMYK 数值。
- **Shift + 单击**：固定取样点；调整参数后，取样值会自动更新。
- **Alt / Option**：在图像上的取样点旁显示数值。
- **“左侧显示”**：在清理前的 CMYK 图像与原图之间切换。

## 支持的语言

界面支持**俄语、英语和简体中文**。语言选择器位于顶部“示例”旁边。浏览器会记住所选语言；切换语言无需刷新页面，也不会丢失取样点。

## 格式与保存

支持单页、8 位的 PNG、JPEG 和 TIFF 图像。CMYK 原图必须嵌入 ICC 色彩配置文件；未带配置文件的 RGB 图像按 sRGB 处理。透明区域会合并到白色背景上。暂不支持 PDF、16 位图像和图层。

关闭或刷新页面前，请先下载结果。打开新文件或刷新页面会清空工作会话；原始文件和已下载的文件仍由你保留。请只使用一个标签页：打开第二个标签页会重置当前会话。

## 开发

[构建界面与运行测试](docs/development.zh-CN.md)。界面使用 Adobe Spectrum Web Components；依赖许可证见 [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt)。
