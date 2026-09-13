# S3 Listing · 图片步骤

> 需求与决策见 `PRD_图片.md`。本步骤跑在文案之后，输入是 `runs/<本次>/s3_draft.json`。
> 出图走本机 Codex CLI 自带的 image_gen。**在 Claude Code 里跑 `images.py ref / gen` 时要关闭命令沙箱**，否则 Codex 连不上网（2026-09-13 实测）。

## 步骤

### 1. 写图位规划 `images_plan.json`（模型做，0 次出图）

读 `s3_draft.json` 的买家关心点、文案、待确认清单，按 `PRD_图片.md` 的默认 7 个图位排：

- 图位 2–4 按关心点排序：**高频差评、对标没回应的点排前面**。
- 叠加文字 `headline`、`points` **只用文案里已有的词**（脚本会查），不写〔待填〕里的数字，不写 best / #1。
- 需要未确认规格才能画的图位（尺寸图等），`status` 写 `hold` 并写原因，不编数字。
- 没有实拍图时写 `concept_subject`：按文案和待确认项描述一个合理的改良款外观，供生成概念参考图。
- `locks` 是四项锁，每次出图都会放在提示词最前面：
  - `geometry`：整体结构和比例
  - `material`：材质和外观
  - `scene_scale`：放在哪里、和周围物体的尺度关系
  - `critical_details`：关键细节，按 P0（功能件）/ P1（识别特征）标级

```json
{
  "candidate": "C2",
  "concept_subject": "…",
  "locks": {"geometry": "…", "material": "…", "scene_scale": "…", "critical_details": ["P0: …", "P1: …"]},
  "slots": [
    {"id": "01_main", "purpose": "主图", "mode": "compose_main", "status": "ready",
     "evidence": "亚马逊主图规则", "headline": "", "points": []},
    {"id": "02_…", "purpose": "…", "mode": "codex_edit", "status": "ready",
     "brief": "画面描述（英文）", "evidence": "关心点：… 差评 12/20；五点 1",
     "headline": "BUILT NOT TO COME APART", "points": ["…"]},
    {"id": "05_size", "purpose": "尺寸", "mode": "hold", "status": "hold", "hold_reason": "尺寸未确认"}
  ]
}
```

`mode`：`compose_main`（参考图贴白底，不调模型）、`codex_edit`（保留产品只换环境 / 特写）、`codex_generate`（新场景、新角度）、`hold`。

### 2. 参考图

- 有实拍图：放进 `runs/<本次>/产品图/`，跳过本步。
- 没有：`python3 stages/s3-listing/images.py ref runs/<本次>`，生成 `images/ref/concept_ref.png`。**打开看一眼**：结构不合理就改 `concept_subject` 重跑。

### 3. 出底图

```bash
python3 stages/s3-listing/images.py gen runs/<本次>            # 全部 ready 的 codex 图位，并发 2，失败自动重试 1 次
python3 stages/s3-listing/images.py gen runs/<本次> --only 03_knives   # 只重跑某张
```

### 4. 合成排字

```bash
python3 stages/s3-listing/images.py compose runs/<本次>
```

### 5. 视觉质检（模型看图，写 `images/review.json`）

逐张打开 `images/final/*.jpg`，和参考图对照，每项填 `pass` 或 `fail`：

```json
{
  "02_sturdy": {"geometry": "pass", "material": "pass", "extra_parts": "pass", "text": "pass",
                "compliance": "pass", "verdict": "pass", "note": ""}
}
```

| 项 | 判 fail 的情况 |
|---|---|
| geometry | 格数、结构、比例和参考图不一致 |
| material | 材质、颜色明显变了 |
| extra_parts | 多出参考图没有的部件、配件、Logo、包装 |
| text | 模型自己画了文字、字母、数字；或叠加文字被遮挡、看不清 |
| compliance | 主图有道具或非白底；出现写实人脸；画面暗示文案没写的功能 |

有 fail：改该图位的 `brief` 后 `gen --only` 重跑 1 次；仍 fail 就把该图位改成 `hold` 并写原因。

### 6. 检查并渲染

```bash
python3 stages/s3-listing/images.py check  runs/<本次>
python3 stages/s3-listing/images.py render runs/<本次>
```

产出 `runs/<本次>/s3_images.md`（图位表、质检明细、HOLD 清单）和 `images/preview/`（1000px 预览，入库用）。原图 `images/final/`、`images/raw/` 不入库。
