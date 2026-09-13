# S3 Listing

> 负责人：Dylan　·　v0.3（2026-09-13）。需求与决策见同目录 `PRD.md`。
> 输出字段的最低要求见 `contracts/交接内容.md` 的「S3 Listing」。参考产出：`runs/2026-09-12_bamboo-drawer-organizer/s3_listing.md`。

## 目标

给 S2 选中的候选写一版**美国站英文 Listing**：标题、Item Highlights、五点、长描述、后台搜索词。做到三件事：
1. **回应买家真正关心的点**：来自真实评论（和 Rufus 问题，如有），尤其是对标竞品没回应的点；
2. **每个用到的词都能说出来源和数字**：这是 S4 投广告的弹药；
3. **硬规则由脚本检查**：模型只管写，字符、字节、重复、违禁词交给 `check_listing.py`。

## 输入

| 输入 | 位置 | 没有时 |
|---|---|---|
| 选中候选 Cx | `s2_利润.md`（开发用 `samples/`） | 写「无」→ 本阶段不跑，告诉用户 |
| Cx 的 ASIN、来源词、需求点；在涨词表；竞品品牌 | `s1_选品.md` | 必需 |
| 本产品卖点、规格、品牌名、禁用词、Rufus 问题 | `runs/<本次>/产品信息.md`（模板 `产品信息_模板.md`） | 用 S1 需求点推卖点，规格写〔待填〕 |

## 步骤

所有卖家精灵原始返回存 `runs/<本次>/raw/<工具名>_<参数>.json`，**调用前先看缓存**。

### 1. 读上游，建产品画像（0 次）

整理出：核心品名（英文，1 个）、产品事实（每条标来源：`用户` / `S1` / `推断`）、待填规格清单、品牌黑名单（S1 竞品品牌 + 产品信息里的禁用词）。
**只有 `用户` 来源的规格能写成确定数字**；`S1` 来源的写成改良方向并进待确认清单；`推断` 不写进文案。

### 2. 读对标 Listing（1 次）

- 标题：`raw/product_research_*.json` 里 Cx 的 `title`（免费）。
- 五点、属性表：`asin_detail`，参数 `{"marketplace":站点,"asin":Cx的ASIN}`，存 `raw/asin_detail_<ASIN>.json`。**不返回长描述。**

拆解出：标题结构、五点主题顺序、写到的规格、违规或弱项写法（如 `#1`、`satisfaction` 类承诺）。**只借结构和缺口，不复述原句**（脚本会查连续 8 词重合）。

### 3. 归纳买家关心点（0–1 次）

- 差评：S1 缓存的 `raw/review_*_1-3星.json`（0 次）。
- 好评：`review`，参数 `{"marketplace":站点,"asin":Cx的ASIN,"starList":[4,5],"size":20,"returnFields":"title,content,star,skus,date"}`，存 `raw/review_<ASIN>_4-5星.json`（1 次）。好评看「为什么买、哪些点不能丢」。
- Rufus（可选）：`产品信息.md` 里有粘贴的问题就用；没有就 `status: skipped`，原因写「未提供 Rufus 问题；浏览器自动采集未启用」。**不要编问题。**

每个关心点写：关心点 / 出现次数（写明分母，如「差评 9/20」）/ 1 句买家原话 / 来源文件 / 对标回应了没（是 / 否 / 部分）/ 我们回应位置。至少 3 个。
**对标没回应、买家又高频提的点，是差异化卖点，排进标题或五点第 1–2 条。**

### 4. 取词（1 次，可选再 1 次）

- `traffic_keyword`，参数 `{"request":{"marketplace":站点,"asin":Cx的ASIN,"order":{"field":"trafficPercentage","desc":true},"size":30}}`。
- S1 在涨词没出现在结果里又想用时，`keyword_miner` 用 `keywordList` 一次批量补查（可选）。

### 5. 清洗、打标（0 次）

- 剔除：品牌词（黑名单）、IP 词、不相关词（对标顺带吃到的流量，如 kitchen decor）、有歧义的词。剔除的写进 `unused_keywords` 并注明原因。
- 打标：含产品功能 / 材质 / 场景 → `high`；只是品名或别名 → `relevant`。

### 6. 分层埋词（0 次）

每个词只放一层，低层不重复高层已用的词：

| 层 | 放什么 | 数量 |
|---|---|---|
| 标题 | 核心品名 + 最精准的 1 个 S1 在涨词 + 流量最高的 1–2 个 high 词 | 2–3 |
| Highlights | 标题放不下的场景、材质、长尾词 | 2–4 |
| 五点 | 中频 high 词，每条 1–2 个 | 5–8 |
| 长描述 | 剩下的 high 长尾词、场景词 | 3–6 |
| 后台 | 同义词、别称、拼写变体、前台没有的 relevant 词 | 填到接近 249 字节 |

### 7. 写 draft（0 次）

写 `runs/<本次>/s3_draft.json`，结构见下方。文案规则：

| 字段 | 写法 | 上限（脚本查） |
|---|---|---|
| 标题 | `[Brand]` + 核心品名 + 1–2 个差异点；放得下再加 〔待填：尺寸 / 件数〕，放不下挪到 Highlights；最核心的词放前 40 字符；Title Case | 75 字符（`[Brand]` 按 10、每个〔〕按 12 计）；禁用 `! $ ? _ { } ^ ¬ ¦`；同一词 ≤2 次 |
| Highlights | 标题放不下的材质、场景、规格；一行短语，不重复标题 | 125 字符 |
| 五点 | 5 条，大写短语开头 + ` – ` + 说明。第 1–2 条回应最高频、对标没回应的关心点，第 3 条其他关心点，第 4 条材质与清洁，第 5 条更多用途 | 每条 255 字符 |
| 长描述 | 以一个使用场景开头；2–3 个场景；陈述句 + 具体事实（Rufus / AI 问答更容易引用）；纯文本 | 2000 字符 |
| 后台搜索词 | 小写、空格分隔、无标点、无品牌词、无停用词、不重复前台已有的词 | 249 字节 |

**硬规矩**：
- 没有 `用户` 来源的规格一律 〔待填〕 或 〔待供应商确认：…〕，并进 `todo_confirm`。
- 不写 best、#1、perfect、guaranteed、free shipping、100%、refund 等。
- 不出现任何竞品品牌名、IP 词。

### 8. 检查并渲染（0 次）

```bash
python3 stages/s3-listing/check_listing.py runs/<本次>/s3_draft.json --render
```

有 FAIL 就改 draft 再跑，**最多 2 轮**。仍不过就保留 FAIL 结果照样渲染，在对话里告诉用户哪几项没过，不硬凑。
脚本写出的 `s3_listing.md` 就是本阶段产出，不要手改。

## draft 结构

```json
{
  "meta": {
    "seed": "bamboo drawer organizer", "site": "US", "generated": "2026-09-13",
    "data_period": "…", "upstream": "runs/…/s2_利润.md（选中 C2）、s1_选品.md",
    "candidate": "C2",
    "sellersprite_calls": {"new": 2, "cache": 3, "detail": "asin_detail 1、review 1；缓存 traffic_keyword 1、review 2"}
  },
  "brand_blacklist": ["…"],
  "product_facts": [{"fact": "…", "source": "用户 / S1 / 推断"}],
  "buyer_concerns": [{"concern": "…", "count": "差评 9/20", "quote": "…", "source": "review_B0…_1-3星",
                      "competitor_covered": "否", "our_position": "五点 1"}],
  "benchmark": {"asin": "B0…", "title_structure": "…", "bullet_themes": ["…"],
                "specs_mentioned": ["…"], "gaps": ["…"], "violations": ["…"]},
  "listing": {"title": "…", "highlights": "…", "bullets": ["…", "…", "…", "…", "…"],
              "description": "…", "search_terms": "…"},
  "keywords": [{"keyword": "…", "placement": ["标题"], "source": "traffic_keyword：月搜索量 N，流量占比 X%"}],
  "unused_keywords": [{"keyword": "…", "reason": "…"}],
  "rufus": {"status": "skipped", "reason": "…", "questions": [{"question": "…", "answered_in": "五点 2"}]},
  "todo_confirm": ["…"]
}
```

`placement` 只能用：`标题`、`Highlights`、`五点`、`长描述`、`后台`。来自 S1 的词 `source` 写 `S1 在涨词：…`。

### 9. 图片（接着做）

文案检查通过后，按 `image_prompt.md` 出 7 张图，产出 `s3_images.md`。没装 Codex CLI 时，只写 `images_plan.json` 并告诉用户图片没生成。

## 额度

本阶段卖家精灵 ≤5 次：asin_detail 1、review 1、traffic_keyword 1、keyword_miner 0–1、余量 1。重跑读缓存为 0 次。
