# 演示视频自动生成

把 [`docs/口播稿.md`](../../docs/口播稿.md) 逐句合成配音，用脚本按 [`docs/录制操作手册.md`](../../docs/录制操作手册.md) 操作工作台并抓帧，最后合成 mp4。不需要手动录屏和真人配音。

2026-09-13 实测：3 分 34 秒，1920×1080，约 14MB。

## 依赖

- Python 3、ffmpeg、本机已装的 Google Chrome
- 在本目录建虚拟环境：

```bash
cd workbench/video
python3 -m venv .venv && .venv/bin/pip install edge-tts playwright
```

## 三步生成

```bash
cd workbench/video
.venv/bin/python tts.py        # 1. 逐句合成配音，写 tts/ 和 durations.json（需联网）
.venv/bin/python record.py     # 2. 按台词时长操作工作台并抓帧，写 frames/ 和 timeline.json（约 3.5 分钟）
python3 build.py ~/Desktop/第81组演示.mp4   # 3. 配音按实际时间轴对齐，合成 mp4
```

在 Claude Code 里跑第 1、2 步时要关闭命令沙箱，否则连不上网、起不了浏览器。

## 文件

| 文件 | 作用 |
|---|---|
| `lines.json` | 口播稿拆成的 28 句，`[句子id, 台词]` |
| `tts.py` | edge-tts 合成配音（默认音色 `zh-CN-YunxiNeural`） |
| `record.py` | Playwright 调本机 Chrome，每句开始时执行对应动作（点击、悬停、滚动），CDP screencast 抓高清帧；注入可见鼠标指针和悬停提示（原生 title 提示录不进画面） |
| `build.py` | 按 `timeline.json` 把 28 段配音对齐混音，帧序列转 30fps，输出 mp4 |
| `cover.html` / `ending.html` / `repo.jpg` | 开场封面、结尾页（GitHub 仓库截图） |

## 改台词或动作

- 改台词：改 `lines.json` 后重跑三步。句子 id 不变，动作就不用改。
- 改动作：`record.py` 里 `a_<句子id>` 函数，在该句开始时执行。
- 单个动作出错最多卡 4 秒，并在终端打印 `action error`，跑完先看有没有这行。

## 已知限制

- 配音是 AI 合成，不是真人。
- 结尾页的 GitHub 截图是静态图，仓库更新后要重新截。
- 中间产物（`tts/`、`frames/`、`timeline.json`、`durations.json`、`.venv/`、mp4）不入库。
