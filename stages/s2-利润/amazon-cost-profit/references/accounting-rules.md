# 核算规则与标准 CSV 字段

## 统一费用分类

| 模块 | `category` 值 | 归属 |
|---|---|---|
| 收入 | `product_revenue`、`buyer_shipping`、`promotion_discount`、`refund` | 前两项增加净销售，后两项减少净销售 |
| 商品成本 | `product_cogs`、`packaging`、`prep_qc` | 直接成本 |
| 运输与入仓 | `domestic_freight`、`international_freight`、`duty`、`inbound_placement` | 直接成本 |
| 平台与履约 | `referral_fee`、`per_item_fee`、`fba_fulfillment`、`fba_storage`、`fbm_warehouse`、`fbm_pick_pack`、`fbm_last_mile`、`other_platform_fee` | 直接成本 |
| 广告与促销服务 | `ads`、`coupon_fee`、`promo_service_fee` | 广告成本 |
| 售后与损耗 | `return_processing`、`damage_loss`、`removal_disposal`、`compensation` | 直接成本；`compensation` 为正数时抵减售后成本 |
| 资金费用 | `payment_fee`、`fx_fee`、`financing_fee` | 直接成本 |
| 其他 | `other_direct`、`fixed_cost`、`marketplace_tax` | 固定费用优先直接归属；税款仅展示，不计利润 |

所有 `amount_usd` 填正数。退款、折扣和各类成本由 `category` 决定方向；不要在金额前再加负号，除非是在冲销既有记录，并在 `source_reference` 标识原因。

## 上架前模板

`estimate_parameters.csv` 的成本字段有两类：`*_cny` 用提供的 `fx_cny_per_usd` 转成 USD；`*_usd` 直接使用。`referral_fee_rate` 填小数，如 15% 填 `0.15`。`target_profit_margin` 可留空；若填写，填小数，如 15% 填 `0.15`。

FBA 行的 `fbm_*` 填 `0`，FBM 行的 `fba_*` 与 `inbound_placement_usd` 填 `0`。`expected_units` 和 `fixed_cost_usd` 共同决定固定费用的单件分摊。广告可填 `ads_per_unit_usd`，或同时填 `ad_spend_usd` 与 `ad_attributed_orders` 自动计算 CPA。两种方式同时填写时，以单件广告成本为准。

`ads_cost_status`、`storage_cost_status`、`fixed_cost_status` 只能填 `included`、`excluded` 或 `unknown`。除 `included` 外，结果会被标为 `partial`。佣金与 FBA 费用的来源和生效日期填入对应 `*_source`、`*_effective_date` 字段。

保本与目标售价会按候选售价重新计算销售佣金的百分比或最低收费，不采用「当前佣金金额不变」的错误算法。广告上限是单件广告前贡献利润，属于单位经济模型上限，不能称为保本 ACoS。

## 月度实际模板

`monthly_income_expense.csv` 是规范明细，不是原始平台导出。字段含义如下：

| 字段 | 规则 |
|---|---|
| `month` | 核算月份，`YYYY-MM`。|
| `date` | 入账或广告发生日期，`YYYY-MM-DD`。|
| `record_type` | 建议填 `actual`；仅作来源状态记录。|
| `sku` | SKU；无法可靠匹配时留空，脚本会输出 `STORE_UNALLOCATED`。|
| `fulfillment_channel` | `FBA`、`FBM` 或店铺级费用留空。|
| `currency` | 首版只接受 `USD`。先在映射环节换汇。|
| `amount_usd` | 金额，填正数。|
| `units` | 关联件数；费用无法按件对应时可留空。|
| `category` | 必须使用上表的标准分类。|
| `source` | 如 `Seller Central settlement`、`Ads report`、`freight invoice`。|
| `source_reference` | 脱敏的报表期、账单号或文件名；不得填订单号或买家信息。|
| `estimated_amount_usd` | 可选。填写后输出同一分类的实际－预估差异。|

先将各原始报表映射到这个表，再运行脚本。对每个导入批次保留原始文件名、日期范围和总金额；导入前后按来源总额对账。广告费用若无法可靠归属 SKU，留空 SKU，结果会保留在店铺未分配项。需要自动计算 CPA、ACoS、TACoS 时，使用 `ad_performance.csv`，不要再把同一广告花费重复填入本表。

`marketplace_tax` 会单独输出，且不会进入利润。`compensation` 填正数，系统会抵减售后成本；退款、退货处理、移除和弃置仍分开填，便于追踪售后损耗。

## 对账检查

1. 销售、退款、佣金和 FBA 费用以结算明细总额为准；广告以广告报表总额为准，两者不能因同一笔广告扣款重复记录。
2. 使用包税物流报价时，不再额外添加已包含的税费或清关费。
3. 商品成本以已售数量的成本为准，而不是整批采购付款额。样例中采购 100 件但售 100 件；若只售一部分，必须仅填已售部分成本。
4. `monthly_profitability.csv` 中 SKU 行与 `STORE_UNALLOCATED` 行相加，应能回到已导入的收入和费用总额；未定义分类会进入报告异常，必须修正后再定稿。
