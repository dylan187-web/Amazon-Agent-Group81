# S3 Listing · 样例产出

> ⚠️ **全部虚构，仅供下游开发对接字段。** 不要引用。v0.3 格式：真实产出由 `stages/s3-listing/check_listing.py` 从 `s3_draft.json` 渲染，真实示例见 `runs/2026-09-12_bamboo-drawer-organizer/s3_listing.md`。

种子词：bamboo drawer organizer
站点：US
生成时间：2026-09-13（样例）
数据周期：虚构
上游文件：samples/s2_利润.md

针对候选：C1

## 买家关心点 → 卖点

| 关心点 | 次数 | 买家原话 | 来源 | 对标回应了没 | 我们回应位置 |
|---|---|---|---|---|---|
| 尺寸不合抽屉 | 差评 6/20（虚构） | "doesn't fit my drawer"（虚构） | review（虚构） | 否 | 标题、五点 1 |
| 隔板不结实 | 差评 4/20（虚构） | "dividers came loose"（虚构） | review（虚构） | 部分 | 五点 2 |
| 在抽屉里打滑 | 好评 2/20（虚构） | "slides around"（虚构） | review（虚构） | 否 | 五点 4 |

## 对标 Listing 拆解（虚构 ASIN）

- **标题结构**：核心词 + 用途 + 同义词重述（虚构）
- **缺口（我们要补的）**：没写宽度可调范围；没提防滑

## 标题

[Brand] Adjustable Bamboo Drawer Organizer, Kitchen Drawer Dividers

## Item Highlights

Expandable drawer organizer for narrow and wide drawers, 〔待填：格数〕 compartments

## 五点描述

1. FITS NARROW AND WIDE DRAWERS – Adjusts from 〔待填〕 to 〔待填〕 inches to fit the drawer you have.
2. SOLID BAMBOO DIVIDERS – 〔待供应商确认：工艺〕 dividers stay in place with daily use.
3. SEPARATES EVERYTHING – Keeps utensils, cutlery and tools in their own slots.
4. NON-SLIP BASE – 〔待供应商确认：防滑垫数量〕 pads keep it from sliding when you open the drawer.
5. EASY SETUP – No tools needed.

## 长描述

Open the drawer and find every fork, spoon and spatula in its own slot. This expandable drawer organizer adjusts to the drawer you already have...（虚构）

Size: 〔待填〕

## 后台搜索词

utensil tray cutlery holder silverware wooden

## 关键词清单

| 词 | 放在哪 | 来源 |
|---|---|---|
| bamboo drawer organizer | 标题 | S1 在涨词 |
| kitchen drawer dividers | 标题 | traffic_keyword（虚构） |
| expandable drawer organizer | Highlights | S1 在涨词 |
| utensil tray | 后台 | traffic_keyword（虚构） |
| silverware holder | 后台 | traffic_keyword（虚构） |
| kitchen drawer organizer | 长描述 | traffic_keyword（虚构） |

`放在哪` 的取值：`标题`、`Highlights`、`五点`、`长描述`、`后台`。

## Rufus 买家问题覆盖

本次跳过：未提供 Rufus 问题（样例）

## 上架前待确认

- [ ] 品牌名
- [ ] 宽度范围、格数、防滑垫数量

## 检查结果（check_listing.py）

全部通过（样例）

---

卖家精灵调用：新调用 0 次 / 读缓存 0 次（样例）
