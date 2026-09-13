---
name: amazon-cost-profit
description: 核算亚马逊美国站 FBA 与 FBM 的上架前单品利润和月度实际 SKU 利润。适用于成本测算、保本定价、广告承受空间和经营复盘，不用于税务申报或自动抓取 Seller Central 数据。
metadata:
  short-description: 亚马逊美国站成本与利润核算
---

# 亚马逊成本与利润核算

输出可追溯的所得税前管理利润，默认 USD。支持两种入口：

- **上架前测算**：依据 SKU 参数计算单件成本、贡献利润、经营利润、保本价、目标利润售价和压力测试。
- **月度实际核算**：依据已映射的标准明细，按「月份＋SKU＋FBA／FBM」汇总实际利润、未分配费用和预估差异。

先读取 [核算规则](references/accounting-rules.md)。处理 Seller Central、广告或物流原始报表时，再读取 [原始报表映射与对账](references/source-mapping.md)；不得直接猜测费率、币种或缺失成本。

## 使用流程

1. 上架前先运行美国站商品费用决策闸门，并读取 [决策规则](references/us-fee-gate.md)：

```bash
python3 scripts/fee_gate.py product_fee_profile.csv --output-dir fee-gate-output
```

2. 仅 `standard_formula_allowed` 的 SKU 可直接使用普通公式。`manual_fee_override_required` 的 SKU 必须先提供 Fee Preview、Revenue Calculator 或实际费用；`blocked` 的 SKU 不输出利润结论。
3. 导入原始 CSV 时，先运行保守导入器；它仅映射能确认的标准字段：

```bash
python3 scripts/import_reports.py --settlement settlement.csv --ads ads.csv --output-dir import-output
```

4. 检查 `unmapped_raw_rows.csv`。存在未映射行时，先人工分类，不能直接把导入结果定稿。
5. 确认范围为美国站，并为每个 SKU 标识 `FBA` 或 `FBM`。同一 SKU 两种配送方式必须分成两行。
6. 选择入口，复制对应模板到工作目录。每项适用费用必须填数值；不适用填 `0`；未知留空并在输出中列为待补充。
3. 运行脚本：

```bash
python3 scripts/calculate_profit.py estimate estimate_parameters.csv --output-dir output
python3 scripts/calculate_profit.py actual monthly_income_expense.csv --output-dir output
python3 scripts/calculate_profit.py actual monthly_income_expense.csv --ad-performance ad_performance.csv --source-manifest source_manifest.csv --inventory-batches inventory_batches.csv --unmapped-rows unmapped_raw_rows.csv --output-dir output
```

4. 读取输出 CSV 和 Markdown 报告，先处理数据质量异常，再将利润结论用于定价或经营决策。

## 输入与输出

- `assets/estimate_parameters.csv`：上架前测算模板；单行是一种 SKU／配送方式。
- `assets/product_fee_profile.csv`：美国站费用决策闸门的商品档案模板。
- `assets/settlement_export_sample.csv`、`assets/ads_export_sample.csv`：支持字段的原始 CSV 示例。
- `fee_gate.csv` 与 `fee_gate_report.md`：商品是否可走普通公式、必须补齐的费用与阻塞原因。
- `monthly_income_expense.csv`、`ad_performance.csv`、`source_manifest.csv`：导入器自动生成的核算输入。
- `unmapped_raw_rows.csv` 与 `ingestion_report.md`：未识别费用与导入质量报告。
- `assets/monthly_income_expense.csv`：月度实际核算模板；单行是一笔已标准化的收入或费用。
- `estimated_profitability.csv`：单品测算、保本价、目标利润售价、广告上限与压力测试。
- `monthly_profitability.csv`：SKU 实际利润；`STORE_UNALLOCATED` 是不能可靠归属 SKU 的店铺级金额。
- `monthly_variance.csv`：只在输入 `estimated_amount_usd` 时生成实际与预估的分类差异。
- `ad_efficiency.csv`：由广告花费、归因订单和归因销售额计算 CPA、ACoS、TACoS。
- `source_reconciliation.csv`：按来源与参考号核对已映射金额；存在 `unmatched` 时不可将利润视为定稿。
- `inventory_cogs_generated.csv`：启用批次表时生成的移动加权平均已售成本。
- `estimate_report.md` 或 `actual_report.md`：汇总结果、亏损 SKU 和数据质量异常。

## 必须遵守的口径

- 净销售收入＝商品收入＋买家支付运费－卖家承担折扣－退款。平台代收代缴税单列，不计利润。
- 广告前贡献利润＝净销售收入－商品成本－物流履约－平台费用－售后损耗－资金费用－其他直接费用。
- 广告后贡献利润＝广告前贡献利润－广告费用；经营利润＝广告后贡献利润－固定费用。
- FBA 可记录配送、仓储、入仓配置、退货处理、移除或弃置等费用；FBM 单列仓储、拣配和尾程。不要把两种配送方式混算。
- 月度实际采用平台入账月份和广告发生月份；跨月退款在退款发生月入账。结算打款只用于对账，不等同收入或利润。
- 共享固定费用仅按正净销售收入分摊。无 SKU 的广告、费用或收入保留为 `STORE_UNALLOCATED`，不要伪装成 SKU 精确成本。
- 人民币成本必须使用用户明确提供的 `fx_cny_per_usd` 换成 USD，并在结论里写出「1 USD＝X CNY」。
- 上架前结果中的 `coverage_status` 必须随结论一起看。广告、仓储或固定费用为 `excluded`／`unknown` 时，利润只能称为部分覆盖测算。

## 边界与检查

- 销售佣金、FBA 配送费等费率以用户提供的类目、尺寸重量、官方计算器或结算实际为准；记录来源和生效日期。官方计算器仅为预估，不能替代实际扣费。
- 费用决策闸门默认将超过 90 天的 FBA 费用来源标为 `stale`，并要求更新 Fee Preview／Revenue Calculator；可用 `--max-fee-age-days` 调整检查周期。
- 采购付款不等于当月销售成本。实际核算优先使用可追溯的已售单位成本；具有完整库存记录时使用月度加权平均。
- `marketplace_tax` 在月度输出中单列，仅用于对账，不计入利润。
- 不把空值当作零。脚本会将缺字段或未知类别写入异常；此时结论必须标为「估算」或「待补充」，不能给确定利润。
- 输出不得含买家姓名、地址、订单号、账号凭据等原始敏感信息。
