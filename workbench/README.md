# 工作台（演示用）

把一次运行的 S1–S4 产出做成可视化界面，用于录屏和现场演示。需求见 [`docs/工作台PRD.md`](../docs/工作台PRD.md)。

## 用法

```bash
# 1. 打包数据（换一次运行就重跑这一行）
python3 workbench/build.py runs/2026-09-12_bamboo-drawer-organizer

# 2. 双击打开，或者：
open workbench/index.html
```

仓库里已经附带参考运行打包好的 `data.js`，clone 下来可以直接打开。

## 说明

- **这是回放，不是实时运行**：页面不调用卖家精灵和大模型，也不需要 key。真实运行在 Claude Code / Codex 里说「对 `<种子词>` 跑一遍」。
- 页面上的数字全部来自 `runs/<本次>/` 的产出文件，由 `build.py` 解析，HTML 里没有手写数字。
- 点任意关键词，其他页面里同一个词会一起高亮；鼠标悬停在虚线下划线的数字上，可以看到来源。
- 首页点 → 按钮，回放四个阶段依次完成的过程。
