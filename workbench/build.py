#!/usr/bin/env python3
"""把一次运行的 S1–S4 产出打包成工作台用的 data.js（只用标准库）。

用法（从仓库根目录）：
    python3 workbench/build.py runs/2026-09-12_bamboo-drawer-organizer

页面上的每个数字都从这里读出来，不在 HTML 里手写。
输出 data.js 而不是 JSON：浏览器用 file:// 直接打开 index.html 时不能 fetch 本地文件。
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CALLS = re.compile(r"新调用\s*(\d+)\s*次\s*/\s*读缓存\s*(\d+)\s*次")


def table(text, first_header):
    """取表头第一列为 first_header 的 Markdown 表格，返回 [{列名: 值}]。"""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        cells = split_row(line)
        if cells and cells[0] == first_header:
            header, rows = cells, []
            for row in lines[i + 1:]:
                if not row.strip().startswith("|"):
                    break
                vals = split_row(row)
                if all(re.fullmatch(r":?-+:?", v) for v in vals):
                    continue
                rows.append(dict(zip(header, vals)))
            return rows
    return []


def split_row(line):
    line = line.strip()
    if not line.startswith("|"):
        return []
    return [c.strip() for c in re.split(r"(?<!\\)\|", line)[1:-1]]


def header_field(text, label):
    found = re.search(r"^" + label + r"[：:]\s*(.+)$", text, re.M)
    return found.group(1).strip() if found else ""


def bold_line(text, label):
    found = re.search(r"\*\*" + label + r"\*\*[：:]\s*(.+)$", text, re.M)
    return found.group(1).strip() if found else ""


def calls(text):
    found = CALLS.search(text)
    return {"new": int(found.group(1)), "cache": int(found.group(2))} if found else None


def section(text, title):
    found = re.search(r"^## " + re.escape(title) + r"\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return found.group(1).strip() if found else ""


def build(run):
    run = run.resolve()
    s1 = (run / "s1_选品.md").read_text(encoding="utf-8")
    s2 = (run / "s2_利润.md").read_text(encoding="utf-8")
    s3md = (run / "s3_listing.md").read_text(encoding="utf-8")
    s3 = json.loads((run / "s3_draft.json").read_text(encoding="utf-8"))
    s4md = (run / "s4_广告.md").read_text(encoding="utf-8")
    s4 = json.loads((run / "s4_draft.json").read_text(encoding="utf-8"))

    rows2 = [r for r in table(s2, "候选编号") if r.get("成本口径") in ("估算", "用户成本")]
    for r in rows2:
        m = re.search(r"\$([\d.,]+)\s*/\s*件", r.get("利润估算", ""))
        r["每件剩"] = m.group(1) if m else ""
    selected = re.search(r"选中候选[：:]\s*\**`?(C\d+|无)", s2)

    images = []
    images_md = run / "s3_images.md"
    if images_md.exists():
        for r in table(images_md.read_text(encoding="utf-8"), "图"):
            m = re.search(r"\((images/[^)]+)\)", r.get("图", ""))
            images.append({
                "slot": r.get("图位", ""), "purpose": r.get("目的", ""), "basis": r.get("依据", ""),
                "overlay": r.get("叠加文字", ""), "qc": r.get("质检", ""),
                "src": ("../" + run.relative_to(HERE.parent).as_posix() + "/" + m.group(1)) if m else "",
            })

    check3 = section(s3md, "检查结果（check_listing.py）").splitlines()
    return {
        "run": run.name,
        "seed": header_field(s1, "种子词"),
        "site": header_field(s1, "站点"),
        "s1": {
            "period": header_field(s1, "数据周期"),
            "rising": table(s1, "词"),
            "candidates": table(s1, "候选编号"),
            "judgement": bold_line(s1, "判断"),
            "common_need": bold_line(s1, "跨竞品的共同需求"),
            "calls": calls(s1),
        },
        "s2": {
            "rows": rows2,
            "selected": selected.group(1) if selected else "",
            "calls": calls(s2),
        },
        "s3": {
            "candidate": header_field(s3md, "针对候选"),
            "period": header_field(s3md, "数据周期"),
            "listing": s3["listing"],
            "concerns": s3["buyer_concerns"],
            "gaps": s3.get("benchmark", {}).get("gaps", []),
            "keywords": s3["keywords"],
            "unused": s3.get("unused_keywords", []),
            "todo": s3.get("todo_confirm", []),
            "check": check3[0] if check3 else "",
            "images": images,
            "calls": calls(s3md),
        },
        "s4": {
            "strategy": s4["meta"].get("strategy_version", ""),
            "period": s4["meta"].get("data_period", ""),
            "ads": s4["ads"], "deferred": s4["deferred"], "negatives": s4["negatives"],
            "budgets": s4["budgets"], "daily_budget": s4.get("daily_budget"), "notes": s4["notes"],
            "passed": "结构校验通过" in s4md,
            "calls": calls(s4md),
        },
    }


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    data = build(Path(sys.argv[1]))
    missing = [k for k, v in (("S1 在涨词", data["s1"]["rising"]), ("S1 候选", data["s1"]["candidates"]),
                              ("S2 候选", data["s2"]["rows"]), ("S4 投放词", data["s4"]["ads"])) if not v]
    if missing:
        raise SystemExit("没解析到：" + "、".join(missing) + "。检查产出文件格式是否符合 contracts/交接内容.md")
    out = HERE / "data.js"
    out.write_text("window.RUN = " + json.dumps(data, ensure_ascii=False, indent=1) + ";\n", encoding="utf-8")
    print(f"已写入 {out}：在涨词 {len(data['s1']['rising'])}、候选 {len(data['s1']['candidates'])}、"
          f"选中 {data['s2']['selected']}、投放词 {len(data['s4']['ads'])}、图片 {len(data['s3']['images'])}")


if __name__ == "__main__":
    main()
