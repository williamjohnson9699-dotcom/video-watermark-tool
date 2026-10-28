# 批量视频水印工具

Windows 10/11 64 位本地工具。支持顶部固定中文水印、碰边反弹文字水印、每个视频随机出现六次的图片水印，以及按视频选择的随机 15 秒片头。

## 下载使用

打开本仓库 Releases，下载 v4.1 的 Windows ZIP，完整解压后运行 `可选片头水印版-v4.1.exe`。无需安装 Python。请保留同目录的 `_internal` 和 `ffmpeg.exe`。

## 功能

- 批量导入视频，统一输出 MP4（H.264 / AAC），保留原文件。
- 顶部固定文字：顶部居中、全程显示，可调整字号、颜色、不透明度与顶部间距。
- 反弹文字：支持中文和字体文件，可调整大小、不透明度、颜色与移动速度。
- 随机图片：选择一张或多张图片，每个视频出现六次，时间、位置和图片随机，六段不重叠。
- 可选片头：默认不生成。在列表选择视频后点击“生成片头：标记选中”，仅标记的视频额外生成随机连续 15 秒片头，文件名以“片头”结尾。短于 15 秒时使用完整时长。
- 重名自动编号，支持停止处理，单个失败后继续处理后续视频。

图片默认每次显示 3 秒，短视频自动缩短；不足 1.2 秒时不支持六次图片水印。片头继承所截时间段的水印，不会重新安排六次图片。界面动画仅为反弹文字示意。

## 源码运行与打包

需要 Windows、Python 3.12（包含 Tkinter）：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python build.py
```

构建后 `dist/VideoWatermark/` 为便携版目录，`dist/video-watermark-v4.1-windows-x64.zip` 为完整压缩包。
构建脚本从已安装的 imageio-ffmpeg 包中复制 FFmpeg；首次安装依赖需要联网。
源码调试时先把 FFmpeg 放到 `watermark.py` 旁并命名为 `ffmpeg.exe`，然后运行 `python watermark.py`。

所有处理均在本地执行。默认中文字体为 Windows 微软雅黑，可自行选择字体文件。HDR、透明视频和特殊色彩空间未专门适配；Mac/Linux 未打包支持。

## 第三方组件

使用 Python、Tkinter、Pillow、PyInstaller 和 FFmpeg。随附 FFmpeg 7.1 由 imageio-ffmpeg 0.6.0 分发，构建标识为 gyan.dev essentials。详细许可和构建参数见 FFMPEG-LICENSE.txt。各组件遵循其自身许可。

- https://ffmpeg.org/
- https://github.com/imageio/imageio-ffmpeg
- https://www.gyan.dev/ffmpeg/builds/

v4.1：加入逐视频片头标记，默认不生成片头。
