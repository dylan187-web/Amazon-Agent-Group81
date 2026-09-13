# 美国站商品费用决策闸门

在任何上架前利润测算前运行 `product_fee_profile.csv`。闸门只决定计算路径，不维护可能随平台更新的费率。

| 结果 | 含义 | 后续动作 |
|---|---|---|
| `standard_formula_allowed` | 商品信息完整，未触发特殊规则。 | 将费用来源与生效日期写入测算模板后计算。 |
| `manual_fee_override_required` | 佣金、履约或项目费用不能由普通公式可靠计算。 | 以 Revenue Calculator、Fee Preview 或结算实际费用覆盖模板字段。 |
| `blocked` | SKU、配送方式、Amazon fee category 或售价缺失。 | 补齐商品档案，不输出利润结论。 |

## 必须触发人工费用覆盖

- 分段佣金类目：Appliances - Compact、Baby Products、Beauty, Health, and Personal Care、Clothing and Accessories、Electronics Accessories、Fine Art、Furniture、Grocery and Gourmet、Jewelry、Lawn Mowers and Snow Throwers、Watches。
- 媒体类：Books、DVD、Music、Software、Video。除佣金外，需核对 closing fee。
- FBA 缺少包装尺寸、重量或当前 FBA 费用来源。
- 套装、危险品、超大件、低价 FBA、AWD、MCF、Subscribe & Save、Vine、FBA New Selection、退货重新入库。

Amazon 的 fee category 不一定等于买家页面展示的分类，因此优先使用 Seller Central／Fee Preview 显示的费用类目。推荐把 Revenue Calculator 或 Fee Preview 的结果视为费用输入来源，保留生效日期；它们仍是估算，月度复盘以结算实际为准。
