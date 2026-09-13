# S2 利润和预算测算

> 负责人：Snow　·　核算引擎：同目录 `amazon-cost-profit/`（Snow 开发的独立 Skill，规则见其 `SKILL.md` 与 `references/accounting-rules.md`）
> 本文件是**对接层**：把 S1 的候选接进 Snow 的核算脚本，再按 `contracts/交接内容.md` 的「S2 利润核算」输出。

## 输入

| 输入 | 位置 | 没有时 |
|---|---|---|
| 候选竞品表（候选编号、ASIN、价格） | `s1_选品.md`（开发用 `samples/s1_选品.md`） | 必需 |
| 售价、FBA 费 | S1 缓存 `raw/product_research_*.json` 的 `price`、`fba` 字段（0 次调用）；缺的候选调 `asin_detail`（每个 1 次） | 写「未查到」 |
| 用户成本 | `runs/<本次>/成本.csv`（模板 `stages/s2-利润/成本输入_模板.csv`） | 走路径 A |

## 两条路径

Snow 的脚本**任何一项成本为空都会拒算这一行**（实测），所以：

### 路径 A：用户没给成本 → 估算（不调脚本）

1. 每个候选：`剩余 = 售价 − FBA 费 − 售价 × 15%`，比例 = 剩余 ÷ 售价。
2. 利润估算写成「扣掉 FBA 费和佣金后剩 $X / 件（Y%），未扣采购、头程、广告」，成本口径写 `估算`。
3. 结论（阈值可改）：剩余 ≥ $15 且 S1 显示销量在涨 → `值得做`；$8–15 → `观望`；< $8 → `放弃`。

### 路径 B：用户给了成本 → 调 Snow 的核算脚本

1. **生成参数表** `runs/<本次>/s2_estimate_parameters.csv`：表头照抄 `amazon-cost-profit/assets/estimate_parameters.csv`，每个候选一行，`sku` 填候选编号（C1、C2…）。
   - 售价、FBA 费：来自 S1 缓存；`referral_fee_rate` 默认 `0.15`，来源写 `SellerSprite product_research`，日期写查询日。
   - 采购、包装、头程、关税、汇率、单件广告、退货损耗：来自 `成本.csv`。
   - FBA 模式下 `fbm_*` 三项填 `0`；`成本.csv` 里明确写「不适用」的填 `0`。
   - **用户没给、又不是不适用的项，不许填 0**：在对话里向用户要，或停在路径 A。
2. **运行**：
   ```bash
   python3 stages/s2-利润/amazon-cost-profit/scripts/calculate_profit.py estimate runs/<本次>/s2_estimate_parameters.csv --output-dir runs/<本次>/s2_output
   ```
3. **读取** `s2_output/estimated_profitability.csv`，每个候选取：
   | 脚本字段 | 写进 `s2_利润.md` |
   |---|---|
   | `operating_profit_per_unit`、`operating_margin` | 利润估算：单件经营利润 $X（Y%） |
   | `breakeven_price` | 保本售价 |
   | `max_ad_spend_per_unit` | **单件广告上限**（给 S4 定预算用） |
   | `stress_post_ads_profit_per_unit` | 压力测试后单件利润 |
   | `coverage_status`、`uncovered_items` | 覆盖情况：不是 `complete` 就在理由里写明缺什么 |
4. 成本口径写 `用户成本`。
5. 结论（阈值可改）：`operating_margin` ≥ 15% 且压力测试后仍盈利 → `值得做`；5%–15% → `观望`；< 5% 或亏损 → `放弃`。报告里有「异常」时，最高只能给 `观望`。

## 输出 `s2_利润.md`

按 `contracts/交接内容.md` 的「S2 利润核算」写，另外加两列（路径 B 才有，路径 A 写「—」）：`保本售价`、`单件广告上限`。

最后一行：**选中候选：`Cx`**（第一个 `值得做`）；没有就写「无」，流程停止。

## 额度

路径 A、B 都优先读 S1 缓存，通常 0 次；缺价格或 FBA 费的候选每个 `asin_detail` 1 次，总计 ≤5 次。
