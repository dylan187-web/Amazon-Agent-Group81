#!/usr/bin/env python3
"""Conservatively map common Amazon US settlement and ads CSV exports to skill inputs."""
from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path


def key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def value(row: dict[str, str], *aliases: str) -> str:
    indexed = {key(name): raw for name, raw in row.items()}
    for alias in aliases:
        if key(alias) in indexed and indexed[key(alias)] is not None:
            return indexed[key(alias)].strip()
    return ""


def amount(raw: str) -> Decimal | None:
    try:
        return abs(Decimal((raw or "").replace("$", "").replace(",", "").strip()))
    except InvalidOperation:
        return None


def classify_settlement(row: dict[str, str]) -> str:
    text = " ".join((value(row, "transaction-type", "transaction type"), value(row, "amount-type", "amount type"), value(row, "amount-description", "amount description", "description"))).lower()
    if "refund" in text:
        return "refund"
    if any(token in text for token in ("itemprice", "item price", "principal", "product sales")):
        return "product_revenue"
    if any(token in text for token in ("referral", "commission", "selling fee")):
        return "referral_fee"
    if "storage" in text:
        return "fba_storage"
    if any(token in text for token in ("fulfillment", "fba fee", "fba fees")):
        return "fba_fulfillment"
    if "return" in text:
        return "return_processing"
    if any(token in text for token in ("removal", "disposal", "liquidation")):
        return "removal_disposal"
    if "inbound placement" in text:
        return "inbound_placement"
    if any(token in text for token in ("promotion", "coupon", "rebate")):
        return "promotion_discount"
    if "tax" in text:
        return "marketplace_tax"
    return ""


def import_settlement(path: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    mapped, unmapped = [], []
    for row in read_csv(path):
        date = value(row, "posted-date", "posted date", "date/time", "date")
        sku = value(row, "sku", "merchant-sku", "merchant sku")
        raw_amount = value(row, "amount", "amount usd", "total")
        category = classify_settlement(row)
        parsed = amount(raw_amount)
        if not date or parsed is None or not category:
            unmapped.append({"date": date, "sku": sku, "amount": raw_amount, "transaction_type": value(row, "transaction-type", "transaction type"), "amount_type": value(row, "amount-type", "amount type"), "description": value(row, "amount-description", "amount description", "description"), "reason": "无法安全识别日期、金额或费用分类"})
            continue
        mapped.append({"month": date[:7], "date": date[:10], "record_type": "actual", "sku": sku, "fulfillment_channel": value(row, "fulfillment-channel", "fulfillment channel", "fulfillment") or "FBA", "currency": "USD", "amount_usd": str(parsed), "units": value(row, "quantity", "units"), "category": category, "source": "Seller Central settlement", "source_reference": path.stem, "estimated_amount_usd": ""})
    return mapped, unmapped


def import_ads(path: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    mapped, unmapped = [], []
    for row in read_csv(path):
        date, sku = value(row, "date", "start date"), value(row, "advertised sku", "sku")
        spend, sales, orders = amount(value(row, "spend", "cost")), amount(value(row, "sales", "attributed sales", "7 day total sales")), amount(value(row, "orders", "attributed orders", "7 day total orders"))
        if not date or not sku or spend is None or sales is None or orders is None:
            unmapped.append({"date": date, "sku": sku, "amount": value(row, "spend", "cost"), "transaction_type": "ads", "amount_type": "", "description": "", "reason": "无法安全识别广告日期、SKU、花费、归因销售或归因订单"})
            continue
        mapped.append({"month": date[:7], "date": date[:10], "sku": sku, "fulfillment_channel": value(row, "fulfillment_channel", "fulfillment channel") or "FBA", "ad_spend_usd": str(spend), "attributed_orders": str(orders), "attributed_sales_usd": str(sales), "source": "Amazon Ads", "source_reference": path.stem})
    return mapped, unmapped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settlement", type=Path)
    parser.add_argument("--ads", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("import-output"))
    args = parser.parse_args()
    if not args.settlement and not args.ads:
        parser.error("至少提供 --settlement 或 --ads。")
    for path in (args.settlement, args.ads):
        if path and not path.is_file():
            parser.error(f"文件不存在：{path}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    canonical, ads, unmapped = [], [], []
    if args.settlement:
        rows, unknown = import_settlement(args.settlement)
        canonical.extend(rows); unmapped.extend(unknown)
    if args.ads:
        rows, unknown = import_ads(args.ads)
        ads.extend(rows); unmapped.extend(unknown)
    canonical_fields = ["month", "date", "record_type", "sku", "fulfillment_channel", "currency", "amount_usd", "units", "category", "source", "source_reference", "estimated_amount_usd"]
    ad_fields = ["month", "date", "sku", "fulfillment_channel", "ad_spend_usd", "attributed_orders", "attributed_sales_usd", "source", "source_reference"]
    unknown_fields = ["date", "sku", "amount", "transaction_type", "amount_type", "description", "reason"]
    write_csv(args.output_dir / "monthly_income_expense.csv", canonical_fields, canonical)
    write_csv(args.output_dir / "ad_performance.csv", ad_fields, ads)
    write_csv(args.output_dir / "unmapped_raw_rows.csv", unknown_fields, unmapped)
    totals = defaultdict(Decimal)
    for row in canonical:
        totals[(row["month"], row["source"], row["source_reference"])] += Decimal(row["amount_usd"])
    for row in ads:
        totals[(row["month"], row["source"], row["source_reference"])] += Decimal(row["ad_spend_usd"])
    manifest = [{"month": month, "source": source, "source_reference": ref, "expected_mapped_total_usd": str(total)} for (month, source, ref), total in sorted(totals.items())]
    write_csv(args.output_dir / "source_manifest.csv", ["month", "source", "source_reference", "expected_mapped_total_usd"], manifest)
    report = ["# 报表导入报告", "", f"- 已映射结算行：{len(canonical)}。", f"- 已映射广告行：{len(ads)}。", f"- 未映射行：{len(unmapped)}。", "", "未映射行保留在 `unmapped_raw_rows.csv`，不得进入利润计算。"]
    (args.output_dir / "ingestion_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"已写入 {args.output_dir}；结算 {len(canonical)} 行，广告 {len(ads)} 行，未映射 {len(unmapped)} 行。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
