#!/usr/bin/env python3
"""S3 Listing 检查 + 渲染（只用标准库）。

用法：
  python3 stages/s3-listing/check_listing.py runs/<本次>/s3_draft.json            # 只检查
  python3 stages/s3-listing/check_listing.py runs/<本次>/s3_draft.json --render   # 检查并写 s3_listing.md

draft 结构见 stages/s3-listing/prompt.md「draft 结构」。
检查不过退出码为 1；--render 时无论过不过都会写文件，并把检查结果写进去。
品牌黑名单 = draft.brand_blacklist + 同目录 raw/product_research_*.json 的 brand 字段。
防抄袭对照 = 同目录 raw/asin_detail_*.json 的 features。
"""
import argparse
import glob
import json
import os
import re
import sys

TITLE_MAX = 75
HIGHLIGHTS_MAX = 125
BULLET_MAX = 255
DESCRIPTION_MAX = 2000
SEARCH_TERMS_MAX_BYTES = 249
BRAND_RESERVE = 10        # [Brand] 按 10 字符计
PLACEHOLDER_RESERVE = 12  # 标题里每个〔…〕按 12 字符计
COPY_NGRAM = 8            # 和对标五点连续 8 个词相同即判抄袭

TITLE_FORBIDDEN_CHARS = set("!$?_{}^¬¦")
STOPWORDS = {"a", "an", "the", "and", "or", "for", "with", "of", "in", "on", "to",
             "by", "from", "at", "is", "it", "as"}
BANNED_PATTERNS = [
    r"\bbest\b", r"#\s*1\b", r"\bguarantee[ds]?\b", r"\bfree shipping\b", r"\btop[- ]rated\b",
    r"\bbest[- ]?seller\b", r"\b100\s*%", r"\bperfect\b", r"\bamazing\b", r"\bsale\b",
    r"\bdiscount\b", r"\bcheapest\b", r"\bmoney[- ]back\b", r"\brefund\b",
]
PLACEHOLDER_RE = re.compile(r"〔[^〕]*〕")


def words(text):
    return re.findall(r"[a-z0-9]+", PLACEHOLDER_RE.sub(" ", text.lower()))


def stem(w):
    return w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w


def title_length(title):
    t = title.replace("[Brand]", "x" * BRAND_RESERVE)
    t = PLACEHOLDER_RE.sub("x" * PLACEHOLDER_RESERVE, t)
    return len(t)


def contains_keyword(field_text, keyword):
    """整词组出现 → 'exact'；所有词（忽略单复数）都出现 → 'split'；否则 None。"""
    fw = words(field_text)
    kw = words(keyword)
    if not kw:
        return None
    joined = " " + " ".join(fw) + " "
    if " " + " ".join(kw) + " " in joined:
        return "exact"
    stems = {stem(w) for w in fw}
    if all(stem(w) in stems for w in kw if w not in STOPWORDS):
        return "split"
    return None


class Report:
    def __init__(self):
        self.rows = []  # (ok, item, detail)

    def add(self, ok, item, detail=""):
        self.rows.append((bool(ok), item, detail))

    @property
    def passed(self):
        return all(ok for ok, _, _ in self.rows)


def load_brands(run_dir, draft):
    brands = {b.strip() for b in draft.get("brand_blacklist", []) if b and b.strip()}
    for path in glob.glob(os.path.join(run_dir, "raw", "product_research_*.json")):
        try:
            data = json.load(open(path, encoding="utf-8")).get("data") or {}
            items = data.get("items", []) if isinstance(data, dict) else data
            brands.update(i["brand"].strip() for i in items if i.get("brand"))
        except (OSError, ValueError, AttributeError):
            pass
    return sorted(b for b in brands if len(b) >= 3)


def load_benchmark_bullets(run_dir):
    bullets = []
    for path in glob.glob(os.path.join(run_dir, "raw", "asin_detail_*.json")):
        try:
            bullets += json.load(open(path, encoding="utf-8"))["data"].get("features") or []
        except (OSError, ValueError, KeyError, TypeError):
            pass
    return bullets


def ngrams(ws, n):
    return {" ".join(ws[i:i + n]) for i in range(len(ws) - n + 1)}


def check(draft, run_dir):
    r = Report()
    L = draft.get("listing", {})
    title = L.get("title", "")
    highlights = L.get("highlights", "")
    bullets = L.get("bullets", [])
    description = L.get("description", "")
    st = L.get("search_terms", "")
    fields = {"标题": title, "Highlights": highlights, "五点": "\n".join(bullets),
              "长描述": description, "后台": st}

    # 必需字段（contracts + PRD）
    r.add(draft.get("meta", {}).get("candidate"), "针对候选已填", draft.get("meta", {}).get("candidate", ""))
    for name, value in fields.items():
        r.add(value.strip(), f"{name}不为空")

    # 标题
    n = title_length(title)
    r.add(n <= TITLE_MAX, f"标题 ≤{TITLE_MAX} 字符", f"{n}（[Brand] 按 {BRAND_RESERVE}、〔〕按 {PLACEHOLDER_RESERVE} 计）")
    bad = sorted(TITLE_FORBIDDEN_CHARS & set(title))
    r.add(not bad, "标题无禁用字符", " ".join(bad))
    counts = {}
    for w in words(title.replace("[Brand]", "")):
        if w not in STOPWORDS:
            counts[stem(w)] = counts.get(stem(w), 0) + 1
    rep = {w: c for w, c in counts.items() if c > 2}
    r.add(not rep, "标题同一个词 ≤2 次", ", ".join(f"{w}×{c}" for w, c in rep.items()))

    # Highlights / 五点 / 长描述
    r.add(len(highlights) <= HIGHLIGHTS_MAX, f"Highlights ≤{HIGHLIGHTS_MAX} 字符", str(len(highlights)))
    r.add(len(bullets) == 5, "五点正好 5 条", str(len(bullets)))
    long_b = [f"第{i + 1}条 {len(b)}" for i, b in enumerate(bullets) if len(b) > BULLET_MAX]
    r.add(not long_b, f"五点每条 ≤{BULLET_MAX} 字符", "；".join(long_b))
    r.add(len(description) <= DESCRIPTION_MAX, f"长描述 ≤{DESCRIPTION_MAX} 字符", str(len(description)))

    # 后台搜索词
    nb = len(st.encode("utf-8"))
    r.add(nb <= SEARCH_TERMS_MAX_BYTES, f"后台词 ≤{SEARCH_TERMS_MAX_BYTES} 字节", str(nb))
    r.add(re.fullmatch(r"[a-z0-9 ]*", st), "后台词小写、无标点")
    st_words = st.split()
    stop_in = sorted({w for w in st_words if w in STOPWORDS})
    r.add(not stop_in, "后台词无停用词", " ".join(stop_in))
    dup = sorted({w for w in st_words if st_words.count(w) > 1})
    r.add(not dup, "后台词内部不重复", " ".join(dup))
    front = {stem(w) for w in words(" ".join([title, highlights, description] + bullets))}
    overlap = sorted({w for w in st_words if stem(w) in front})
    r.add(not overlap, "后台词不重复前台已有的词", " ".join(overlap))

    # 违禁宣传语、品牌词
    hits = []
    for name, value in fields.items():
        for p in BANNED_PATTERNS:
            m = re.search(p, value, re.I)
            if m:
                hits.append(f"{name}:{m.group(0)}")
    r.add(not hits, "无违禁宣传语", "；".join(hits))
    brand_hits = []
    for b in load_brands(run_dir, draft):
        for name, value in fields.items():
            if re.search(r"(?<![a-z0-9])" + re.escape(b.lower()) + r"(?![a-z0-9])", value.lower()):
                brand_hits.append(f"{name}:{b}")
    r.add(not brand_hits, "无竞品品牌名 / 黑名单词", "；".join(brand_hits))

    # 防抄袭
    ours = ngrams(words(" ".join([title, highlights, description] + bullets)), COPY_NGRAM)
    theirs = set()
    for b in load_benchmark_bullets(run_dir):
        theirs |= ngrams(words(b), COPY_NGRAM)
    copied = sorted(ours & theirs)
    r.add(not copied, f"不抄对标文案（连续 {COPY_NGRAM} 词）", "；".join(copied[:3]))

    # 关键词清单 ↔ 文案
    kws = draft.get("keywords", [])
    r.add(kws, "关键词清单不为空", str(len(kws)))
    missing, no_source = [], []
    for k in kws:
        if not str(k.get("source", "")).strip():
            no_source.append(k.get("keyword", ""))
        for place in k.get("placement", []):
            if place not in fields:
                missing.append(f"{k.get('keyword')}→未知位置 {place}")
            elif place == "后台":
                # 后台词不重复前台，所以词组由「前台 + 后台」拼成即可，但至少 1 个词在后台
                kw = words(k.get("keyword", ""))
                st_stems = {stem(w) for w in st_words}
                if not (contains_keyword(" ".join(fields.values()), k.get("keyword", ""))
                        and any(stem(w) in st_stems for w in kw)):
                    missing.append(f"{k.get('keyword')}→后台")
            elif not contains_keyword(fields[place], k.get("keyword", "")):
                missing.append(f"{k.get('keyword')}→{place}")
    r.add(not missing, "清单里的词都出现在声明位置", "；".join(missing))
    r.add(not no_source, "清单里的词都有来源", "；".join(no_source))

    # 买家关心点
    concerns = draft.get("buyer_concerns", [])
    r.add(len(concerns) >= 3, "买家关心点 ≥3 个", str(len(concerns)))
    unanswered = [c.get("concern", "") for c in concerns if not str(c.get("our_position", "")).strip()]
    r.add(not unanswered, "每个关心点都有回应位置", "；".join(unanswered))

    # Rufus
    rufus = draft.get("rufus", {})
    status = rufus.get("status")
    r.add(status in ("completed", "skipped"), "Rufus 状态为 completed / skipped", str(status))
    if status == "skipped":
        r.add(str(rufus.get("reason", "")).strip(), "Rufus 跳过写明原因")
    if status == "completed":
        qs = rufus.get("questions", [])
        un = [q.get("question", "") for q in qs if not str(q.get("answered_in", "")).strip()]
        r.add(qs and not un, "Rufus 问题逐条有回应位置", "；".join(un))
    return r


def md_table(headers, rows):
    esc = lambda v: str(v).replace("|", "\\|").replace("\n", " ")
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(esc(v) for v in row) + " |" for row in rows]
    return "\n".join(out)


def render(draft, report):
    m = draft.get("meta", {})
    L = draft["listing"]
    b = draft.get("benchmark", {})
    rufus = draft.get("rufus", {})
    calls = m.get("sellersprite_calls", {})
    parts = [
        "# S3 Listing", "",
        f"种子词：{m.get('seed', '')}",
        f"站点：{m.get('site', 'US')}",
        f"生成时间：{m.get('generated', '')}",
        f"数据周期：{m.get('data_period', '')}",
        f"上游文件：{m.get('upstream', '')}", "",
        f"针对候选：{m.get('candidate', '')}", "",
    ]
    if draft.get("product_facts"):
        parts += ["## 产品事实", "", md_table(["事实", "来源"],
                  [[f.get("fact"), f.get("source")] for f in draft["product_facts"]]), ""]
    parts += ["## 买家关心点 → 卖点", "", md_table(
        ["关心点", "次数", "买家原话", "来源", "对标回应了没", "我们回应位置"],
        [[c.get("concern"), c.get("count"), c.get("quote"), c.get("source"),
          c.get("competitor_covered"), c.get("our_position")] for c in draft.get("buyer_concerns", [])]), ""]
    if b:
        parts += [f"## 对标 Listing 拆解（{b.get('asin', '')}）", "",
                  f"- **标题结构**：{b.get('title_structure', '')}",
                  f"- **五点主题顺序**：{' → '.join(b.get('bullet_themes', []))}",
                  f"- **写到的规格**：{'；'.join(b.get('specs_mentioned', []))}",
                  f"- **缺口（我们要补的）**：{'；'.join(b.get('gaps', []))}",
                  f"- **违规或弱项写法**：{'；'.join(b.get('violations', [])) or '暂无'}", ""]
    parts += ["## 标题", "", L["title"], "",
              "## Item Highlights", "", L["highlights"], "",
              "## 五点描述", ""]
    parts += [f"{i + 1}. {x}" for i, x in enumerate(L["bullets"])]
    parts += ["", "## 长描述", "", L["description"], "",
              "## 后台搜索词", "", L["search_terms"], "",
              "## 关键词清单", "", md_table(["词", "放在哪", "来源"],
              [[k.get("keyword"), "、".join(k.get("placement", [])), k.get("source")]
               for k in draft.get("keywords", [])]), ""]
    if draft.get("unused_keywords"):
        parts += ["**有意没用的词**：", ""]
        parts += [f"- {u.get('keyword')}：{u.get('reason')}" for u in draft["unused_keywords"]]
        parts += [""]
    parts += ["## Rufus 买家问题覆盖", ""]
    if rufus.get("status") == "completed":
        parts += [md_table(["问题", "回应位置"],
                  [[q.get("question"), q.get("answered_in")] for q in rufus.get("questions", [])])]
    else:
        parts += [f"本次跳过：{rufus.get('reason', '')}"]
    parts += ["", "## 上架前待确认", ""]
    parts += [f"- [ ] {t}" for t in draft.get("todo_confirm", [])] or ["暂无"]
    parts += ["", "## 检查结果（check_listing.py）", "",
              "全部通过" if report.passed else "**有未通过项，上架前必须处理**", "",
              md_table(["结果", "检查项", "详情"],
                       [["✅" if ok else "❌", item, detail] for ok, item, detail in report.rows]), "",
              "---", "",
              f"卖家精灵调用：新调用 {calls.get('new', 0)} 次 / 读缓存 {calls.get('cache', 0)} 次"
              + (f"（{calls['detail']}）" if calls.get("detail") else ""), ""]
    return "\n".join(parts)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("draft")
    ap.add_argument("--render", action="store_true", help="写同目录 s3_listing.md")
    args = ap.parse_args()
    draft = json.load(open(args.draft, encoding="utf-8"))
    run_dir = os.path.dirname(os.path.abspath(args.draft))
    report = check(draft, run_dir)
    for ok, item, detail in report.rows:
        print(f"{'PASS' if ok else 'FAIL'}  {item}" + (f"  —  {detail}" if detail else ""))
    print("\n结论：" + ("全部通过" if report.passed else "有未通过项"))
    if args.render:
        out = os.path.join(run_dir, "s3_listing.md")
        with open(out, "w", encoding="utf-8") as f:
            f.write(render(draft, report))
        print(f"已写出 {out}")
    sys.exit(0 if report.passed else 1)


if __name__ == "__main__":
    main()
