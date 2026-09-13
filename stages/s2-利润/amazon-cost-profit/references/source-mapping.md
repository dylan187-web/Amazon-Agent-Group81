# 原始报表映射与对账

优先使用 `scripts/import_reports.py` 导入常见 Seller Central 结算 CSV 与广告报表。它输出 `monthly_income_expense.csv`、`ad_performance.csv`、`source_manifest.csv` 和 `unmapped_raw_rows.csv`。未映射行代表费用名称或字段无法被安全识别，必须人工确认分类后再纳入利润。

清单里的 `expected_mapped_total_usd` 是该来源所有已映射标准行 `amount_usd` 的绝对金额合计，用于检查是否漏行或重复映射，不是结算净打款额。

| 原始来源 | 常见映射分类 | 关键检查 |
|---|---|---|
| Seller Central 结算明细 | `product_revenue`、`refund`、`referral_fee`、`fba_fulfillment`、`fba_storage`、`return_processing`、`removal_disposal` | 同一结算周期、币种和总额一致；不要把打款金额再记为收入。 |
| Sponsored Ads 报表 | `ads`，或使用 `ad_performance.csv` | 广告花费只导入一次；归因订单必须大于零才能计算 CPA。 |
| 物流与入仓账单 | `international_freight`、`duty`、`inbound_placement` | 包税报价不能重复填关税或清关费用。 |
| 成本与入库表 | `product_cogs`、`packaging`、`prep_qc`，或使用 `inventory_batches.csv` | 已启用批次成本时，不要再为相同 SKU 导入这三类实际成本。 |

自动导入器目前只自动映射可确认的商品收入、退款、佣金、FBA 配送费、仓储费、退货处理、移除／弃置、入仓配置、促销和税款。头程、关税、采购成本、复杂促销与任何未识别项目仍需用对应模板补充。

运行月度核算时可附加：

```bash
python3 scripts/calculate_profit.py actual monthly_income_expense.csv \
  --ad-performance ad_performance.csv \
  --source-manifest source_manifest.csv \
  --inventory-batches inventory_batches.csv \
  --unmapped-rows unmapped_raw_rows.csv \
  --output-dir output
```

`source_reconciliation.csv` 中只有 `matched` 才表示该来源已按声明的映射范围完整导入。`unmatched` 时，报告仍可生成，但不能作为定稿利润。

`inventory_batches.csv` 使用移动加权平均：每次销售按销售日期之前可用批次的平均单位成本结转。销售收入行必须填写 `units`；库存不足时不会生成成本，并会在报告中报错。批次法首版不自动回冲退款或重入可售库存，这些情况仍需单独记录并人工复核。
