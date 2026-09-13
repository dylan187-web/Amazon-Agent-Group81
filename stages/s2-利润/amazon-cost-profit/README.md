# Amazon Cost & Profit 使用说明

`amazon-cost-profit` 是面向亚马逊美国站的成本与利润核算 Skill，支持 FBA 与 FBM。它用于经营决策：上架前判断产品是否值得销售，或在月度复盘时识别真正赚钱的 SKU。

## 适用范围

- **上架前测算**：计算单件成本、广告前／后贡献利润、经营利润、保本售价、目标利润售价与压力测试。
- **月度实际核算**：导入结算和广告 CSV，按「月份＋SKU＋FBA／FBM」汇总收入、费用、广告效率、利润和预估差异。
- **美国站费用决策闸门**：在测算前判断能否使用普通公式，或必须补充 Fee Preview、Revenue Calculator 或结算实际费用。

默认以 USD 汇总。人民币成本必须填写 `fx_cny_per_usd`，例如 `6.70` 代表「1 USD＝6.70 CNY」。

## 安装与准备

1. 解压压缩包，得到 `amazon-cost-profit` 文件夹。
2. 将该文件夹安装到 Codex 的 Skills 目录，或在已安装的 Skill 环境中使用它。
3. 确认电脑已安装 Python 3。所有命令都在 `amazon-cost-profit` 文件夹内执行。
4. 初次使用建议先查看 `assets/` 中的模板与示例，不要直接覆盖原始模板。

运行前至少准备以下信息：

- SKU 与配送方式：`FBA` 或 `FBM`；同一 SKU 两种方式必须分开核算。
- 售价、采购和包装成本、头程、关税、入仓配置、汇率。
- 类目佣金、FBA／FBM 履约费、广告、退货和固定费用。
- 月度复盘时的 Seller Central 结算 CSV、广告 CSV，以及可追溯的商品成本或库存批次数据。

不适用的费用填 `0`；不确定的费用留空。不要用 `0` 代替未知成本。

## 流程一：上架前利润测算

### 1．运行费用决策闸门

先复制 `assets/product_fee_profile.csv`，填入商品的 Amazon fee category、尺寸、重量、售价和费用来源日期，然后运行：

```bash
python3 scripts/fee_gate.py product_fee_profile.csv --output-dir output/fee-gate
```

查看 `output/fee-gate/fee_gate.csv`：

- `standard_formula_allowed`：商品信息完整，可继续常规测算。
- `manual_fee_override_required`：普通公式不足以可靠计算费用，必须使用 Fee Preview、Revenue Calculator 或实际费用覆盖模板字段。
- `blocked`：SKU、配送方式、费用类目或售价等关键字段缺失，不能输出利润结论。

费用来源默认超过 90 天会被标为 `stale`。此时应更新 Fee Preview 或 Revenue Calculator 的费用数据后再测算。

### 2．填写预估参数表

复制 `assets/estimate_parameters.csv` 为自己的工作文件，例如 `my_estimate.csv`。每行代表一个「SKU＋配送方式」。

需要重点填写：售价、单位商品成本、头程、关税、入仓配置、佣金、履约费、广告、退货、固定费用、月销量和汇率。

### 3．计算并查看结果

```bash
python3 scripts/calculate_profit.py estimate my_estimate.csv --output-dir output/estimate
```

主要结果：

- `output/estimate/estimated_profitability.csv`：SKU 利润、利润率、保本价、目标售价、广告上限与压力测试。
- `output/estimate/estimate_report.md`：汇总结论、待补充字段与数据质量提醒。

若报告中的 `coverage_status` 显示 `excluded` 或 `unknown`，结果只能作为部分覆盖测算，不能当作完整利润。

## 流程二：月度实际利润核算

### 1．导入结算与广告 CSV

从 Seller Central 和 Amazon Ads 导出 CSV 后运行：

```bash
python3 scripts/import_reports.py \
  --settlement settlement.csv \
  --ads ads.csv \
  --output-dir import-output
```

导入器会生成：

- `import-output/monthly_income_expense.csv`：已标准化的收入与费用明细。
- `import-output/ad_performance.csv`：广告花费、归因订单和归因销售额。
- `import-output/source_manifest.csv`：来源映射金额清单。
- `import-output/unmapped_raw_rows.csv`：不能被安全识别的原始行。
- `import-output/ingestion_report.md`：导入质量报告。

导入器只自动映射可以确认的项目，例如商品收入、退款、佣金、FBA 配送费、仓储费、退货处理、移除／弃置、入仓配置、促销和平台代收税款。

采购成本、头程、关税、复杂促销和未识别费用需要人工确认后补充到标准明细中。

### 2．处理未映射费用

必须先检查 `import-output/unmapped_raw_rows.csv`：

- 文件只有表头：可以继续下一步。
- 文件存在数据行：先人工确认费用分类并补录；此时脚本仍可生成报告，但利润结果**不能定稿**。

不要把未识别费用当作零，也不要把平台结算打款金额重复记为收入。

### 3．运行实际核算

基础命令：

```bash
python3 scripts/calculate_profit.py actual \
  import-output/monthly_income_expense.csv \
  --ad-performance import-output/ad_performance.csv \
  --source-manifest import-output/source_manifest.csv \
  --unmapped-rows import-output/unmapped_raw_rows.csv \
  --output-dir output/actual
```

如果拥有完整的采购批次和库存数据，再额外加入：

```bash
--inventory-batches inventory_batches.csv
```

批次成本表采用移动加权平均。库存不足、销售行缺少销量，或退款需要重新入库时，报告会提示人工复核。

主要结果：

- `output/actual/monthly_profitability.csv`：按月份、SKU、FBA／FBM 的实际利润。
- `output/actual/ad_efficiency.csv`：CPA、ACoS、TACoS。
- `output/actual/monthly_variance.csv`：预估与实际差异；仅当输入 `estimated_amount_usd` 时生成。
- `output/actual/source_reconciliation.csv`：来源映射是否对账。
- `output/actual/actual_report.md`：店铺汇总、亏损 SKU、异常与缺失数据。

`source_reconciliation.csv` 中只有 `matched` 才表示对应来源在已声明的映射范围内完成对账。`unmatched` 时，不应将利润作为最终经营结论。

## 核算规则

- 净销售收入＝商品收入＋买家支付运费－卖家承担折扣－退款。
- 广告前贡献利润＝净销售收入－商品成本－物流履约－平台费用－售后损耗－资金费用－其他直接费用。
- 广告后贡献利润＝广告前贡献利润－广告费用。
- 经营利润＝广告后贡献利润－固定费用。
- 平台代收代缴税款单列，用于对账，不计入利润。
- 采购付款不等于当月销售成本。实际核算优先使用可追溯的已售单位成本；库存完整时使用移动加权平均。
- 共享固定费用仅按正净销售收入分摊。无法可靠归属 SKU 的金额保留为 `STORE_UNALLOCATED`。
- 头程包税报价不得再次重复加入关税或清关费用；广告费用也只能导入一次。

## 自动化边界

本 Skill 自动完成本地 CSV 的保守导入、费用分类、来源对账、费用资料时效检查和利润计算。

它不会：

- 自动登录或下载 Seller Central、Amazon Ads 的私有报表。
- 自动抓取或猜测实时平台费率。
- 在关键成本缺失、费用未映射或对账未通过时给出确定利润。
- 用于税务申报。

月度利润只有在关键成本完整、未映射费用已处理、来源状态为 `matched` 的情况下，才可用于最终经营判断。

## 常见问题

**同一 SKU 既有 FBA 又有 FBM，如何处理？**  
分成两行或两套明细，并分别标记配送方式；不要混算。

**没有广告归因订单，还能核算吗？**  
可以计算广告花费和利润，但 CPA 无法计算；广告效率结论需要标记为数据不足。

**只有采购报价，没有库存数据，能算实际利润吗？**  
可以作为估算利润，但不能称为完整的实际销售成本核算。

**费用资料来自旧的 Fee Preview，能继续使用吗？**  
可以查看结果，但超过默认 90 天会触发过期提醒；应更新后再用作定价决策。
