#!/usr/bin/env python3
"""S3 Listing 图片：参考图 → Codex 出底图 → 本地合成排字 → 质检 → 渲染（Python 3 + Pillow）。

用法（RUN = runs/<本次>）：
  python3 stages/s3-listing/images.py ref     RUN   # 没有实拍图时，让 Codex 按图位规划生成 1 张白底概念参考图
  python3 stages/s3-listing/images.py gen     RUN   # 为 mode=codex_* 的图位调用 Codex 出无文字底图（并发 2）
  python3 stages/s3-listing/images.py compose RUN   # 主图贴白底画布；副图加标题和卖点
  python3 stages/s3-listing/images.py check   RUN   # 脚本质检 + 合并视觉质检结论
  python3 stages/s3-listing/images.py render  RUN   # 写 RUN/s3_images.md 和 1000px 预览图

输入：RUN/images_plan.json（结构见 stages/s3-listing/image_prompt.md）、RUN/s3_draft.json、
      可选 RUN/产品图/*.jpg|png（实拍图）、RUN/images/review.json（视觉质检结论）。
出图走本机 Codex CLI 自带的 image_gen（不需要 OPENAI_API_KEY）。
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from PIL import Image, ImageDraw, ImageFont

CANVAS = 2000
MAIN_FILL_MIN = 0.85
MAIN_FILL_TARGET = 0.88
WHITE_EDGE_MIN = 0.99
MAX_BYTES = 10 * 1024 * 1024
PREVIEW = 1000
CODEX_HOME = os.environ.get("CODEX_HOME", os.path.expanduser("~/.codex"))
CODEX_TIMEOUT = 600
FONT_BOLD = ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "C:/Windows/Fonts/arialbd.ttf"]
FONT_REGULAR = ["/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "C:/Windows/Fonts/arial.ttf"]


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def paths(run):
    img = os.path.join(run, "images")
    return {"plan": os.path.join(run, "images_plan.json"), "draft": os.path.join(run, "s3_draft.json"),
            "photos": os.path.join(run, "产品图"), "img": img, "ref": os.path.join(img, "ref"),
            "raw": os.path.join(img, "raw"), "final": os.path.join(img, "final"),
            "preview": os.path.join(img, "preview"), "review": os.path.join(img, "review.json"),
            "logs": os.path.join(img, "logs"), "md": os.path.join(run, "s3_images.md")}


def reference_images(p, plan):
    photos = sorted(glob.glob(os.path.join(p["photos"], "*.[jJpP][pPnN]*[gG]")))
    if photos:
        return photos, False
    concept = os.path.join(p["ref"], "concept_ref.png")
    return ([concept] if os.path.exists(concept) else []), True


# ---------- Codex ----------

def newest_codex_image(since):
    files = [f for f in glob.glob(os.path.join(CODEX_HOME, "generated_images", "**", "*"), recursive=True)
             if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")) and os.path.getmtime(f) >= since]
    return max(files, key=os.path.getmtime) if files else None


def run_codex(prompt, out_path, images, log_path):
    """调用 Codex 出 1 张图，复制到 out_path。成功返回 True。"""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    workdir = os.path.dirname(os.path.abspath(out_path))
    full = (prompt + "\n\nUse your built-in image_gen tool exactly once. Do not render any text, letters, "
            "numbers, logos or watermarks in the image. After generating, copy the image file from "
            f"$CODEX_HOME/generated_images into {os.path.abspath(out_path)} . Reply with only that path.")
    cmd = ["codex", "exec", "--skip-git-repo-check", "-s", "workspace-write",
           "-c", "model_reasoning_effort=low", "-C", workdir]
    for im in images:
        cmd += ["-i", os.path.abspath(im)]
    cmd.append("-")  # -i 会吞掉后面的参数，提示词改走 stdin
    start = time.time()
    with open(log_path, "w", encoding="utf-8") as log:
        try:
            subprocess.run(cmd, input=full, text=True, stdout=log, stderr=subprocess.STDOUT,
                           timeout=CODEX_TIMEOUT, check=False)
        except subprocess.TimeoutExpired:
            log.write(f"\nTIMEOUT after {CODEX_TIMEOUT}s\n")
    if not os.path.exists(out_path) or os.path.getmtime(out_path) < start:
        found = newest_codex_image(start)  # Codex 没复制时，从 generated_images 兜底取
        if found:
            shutil.copy(found, out_path)
    return os.path.exists(out_path) and os.path.getmtime(out_path) >= start


def lock_block(plan):
    locks = plan.get("locks", {})
    details = "\n".join(f"- {d}" for d in locks.get("critical_details", []))
    return ("PRODUCT FIDELITY LOCKS (must follow before anything else):\n"
            f"Geometry: {locks.get('geometry', '')}\n"
            f"Material: {locks.get('material', '')}\n"
            f"Scene scale: {locks.get('scene_scale', '')}\n"
            f"Critical details:\n{details}\n"
            "Keep the product identical to the reference image. Do not add, remove or reshape parts. "
            "Do not invent accessories, labels, logos or packaging. No people except hands without faces.")


def cmd_ref(run):
    p = paths(run)
    plan = load_json(p["plan"])
    photos, _ = reference_images(p, plan)
    if photos and not photos[0].endswith("concept_ref.png"):
        print(f"已有实拍图 {len(photos)} 张，不生成概念图")
        return 0
    out = os.path.join(p["ref"], "concept_ref.png")
    prompt = ("Use case: product-mockup\nAsset type: concept reference photo for an Amazon listing\n"
              f"Subject: {plan.get('concept_subject', '')}\n"
              "Style/medium: realistic studio product photo, three-quarter top view, whole product visible\n"
              "Scene/backdrop: pure white seamless background, soft even light, subtle contact shadow\n\n"
              + lock_block(plan))
    ok = run_codex(prompt, out, [], os.path.join(p["logs"], "concept_ref.log"))
    print(("已生成 " if ok else "失败，见日志 ") + (out if ok else os.path.join(p["logs"], "concept_ref.log")))
    return 0 if ok else 1


def cmd_gen(run, only=None):
    p = paths(run)
    plan = load_json(p["plan"])
    refs, _ = reference_images(p, plan)
    if not refs:
        print("没有参考图：先放实拍图到 产品图/，或运行 images.py ref")
        return 1
    jobs = [s for s in plan["slots"] if s.get("status") == "ready" and s.get("mode", "").startswith("codex")
            and (not only or s["id"] in only)]

    def job(slot):
        prompt = (f"Use case: {'product-mockup' if slot['mode'] == 'codex_edit' else 'photorealistic-natural'}\n"
                  f"Asset type: Amazon listing secondary image, square 1:1, background plate without text\n"
                  "Input images: Image 1 is the product reference — keep this exact product\n"
                  f"Primary request: {slot.get('brief', '')}\n"
                  f"Composition/framing: {slot.get('composition', 'product large and sharp, leave the top 20% of the frame calm and uncluttered for a headline added later')}\n\n"
                  + lock_block(plan))
        out = os.path.join(p["raw"], f"{slot['id']}.png")
        ok = run_codex(prompt, out, refs[:3], os.path.join(p["logs"], f"{slot['id']}.log"))
        if not ok:  # 失败重试 1 次
            ok = run_codex(prompt, out, refs[:3], os.path.join(p["logs"], f"{slot['id']}.retry.log"))
        return slot["id"], ok

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(job, jobs))
    for sid, ok in results:
        print(f"{'OK  ' if ok else 'FAIL'}  {sid}")
    return 0 if all(ok for _, ok in results) else 1


# ---------- 合成 ----------

def font(candidates, size):
    for f in candidates:
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def whiten(img, threshold=240):
    """近白像素归为纯白 255，返回 RGB 图。"""
    import numpy as np
    a = np.array(img.convert("RGB"))
    a[(a >= threshold).all(axis=2)] = 255
    return Image.fromarray(a)


def product_bbox(img, threshold=250):
    gray = img.convert("L").point(lambda v: 255 if v < threshold else 0)
    return gray.getbbox()


def compose_main(src, out):
    img = whiten(Image.open(src))
    box = product_bbox(img)
    if box:
        img = img.crop(box)
    scale = CANVAS * MAIN_FILL_TARGET / max(img.size)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    canvas = Image.new("RGB", (CANVAS, CANVAS), (255, 255, 255))
    canvas.paste(img, ((CANVAS - img.width) // 2, (CANVAS - img.height) // 2))
    save_jpg(whiten(canvas, 250), out, quality=95)  # 缩放产生的近白边再归一次白


def cover(img, size):
    scale = max(size / img.width, size / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left, top = (img.width - size) // 2, (img.height - size) // 2
    return img.crop((left, top, left + size, top + size))


def wrap(draw, text, fnt, width):
    lines, line = [], ""
    for word in text.split():
        test = (line + " " + word).strip()
        if draw.textlength(test, font=fnt) <= width:
            line = test
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def compose_secondary(src, slot, out):
    img = cover(Image.open(src).convert("RGB"), CANVAS)
    draw = ImageDraw.Draw(img, "RGBA")
    pad = 110
    headline = slot.get("headline", "").upper()
    points = slot.get("points", [])
    h_font, p_font = font(FONT_BOLD, 112), font(FONT_REGULAR, 66)
    h_lines = wrap(draw, headline, h_font, CANVAS - 2 * pad)
    band_h = pad + len(h_lines) * 132 + 60
    draw.rectangle([0, 0, CANVAS, band_h], fill=(255, 255, 255, 235))
    y = pad
    for line in h_lines:
        draw.text((pad, y), line, font=h_font, fill=(33, 37, 41, 255))
        y += 132
    if points:
        p_lines = []
        for pt in points[:3]:
            p_lines += ["• " + l if i == 0 else "  " + l for i, l in enumerate(wrap(draw, pt, p_font, CANVAS - 2 * pad - 40))]
        box_h = len(p_lines) * 90 + 2 * 70
        draw.rectangle([0, CANVAS - box_h, CANVAS, CANVAS], fill=(33, 37, 41, 225))
        y = CANVAS - box_h + 70
        for line in p_lines:
            draw.text((pad, y), line, font=p_font, fill=(255, 255, 255, 255))
            y += 90
    save_jpg(img, out)


def save_jpg(img, out, quality=92):
    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.convert("RGB").save(out, "JPEG", quality=quality, subsampling=0, optimize=True)


def final_name(plan, slot, concept):
    return f"{plan.get('candidate', 'Cx')}_{slot['id']}{'_concept' if concept else ''}.jpg"


def cmd_compose(run):
    p = paths(run)
    plan = load_json(p["plan"])
    refs, concept = reference_images(p, plan)
    for slot in plan["slots"]:
        if slot.get("status") != "ready":
            continue
        out = os.path.join(p["final"], final_name(plan, slot, concept))
        if slot["mode"] == "compose_main":
            if not refs:
                print(f"SKIP  {slot['id']}：没有参考图")
                continue
            compose_main(refs[0], out)
        else:
            src = os.path.join(p["raw"], f"{slot['id']}.png")
            if not os.path.exists(src):
                print(f"SKIP  {slot['id']}：没有底图 {src}")
                continue
            compose_secondary(src, slot, out)
        print(f"OK    {out}")
    return 0


# ---------- 质检 ----------

def listing_words(draft):
    L = (draft or {}).get("listing", {})
    text = " ".join([L.get("title", ""), L.get("highlights", ""), L.get("description", "")] + L.get("bullets", []))
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def check_slot(plan, slot, path, is_main, draft):
    rows = []
    img = Image.open(path)
    rows.append((img.size == (CANVAS, CANVAS), "尺寸 2000×2000", f"{img.size[0]}×{img.size[1]}"))
    size = os.path.getsize(path)
    rows.append((size <= MAX_BYTES, "文件 ≤10MB", f"{size // 1024}KB"))
    if is_main:
        rgb = img.convert("RGB")
        w, h = rgb.size
        band = max(1, w // 50)
        px = rgb.load()
        edge = [px[x, y] for y in range(0, h, 4) for x in range(0, w, 4)
                if x < band or y < band or x >= w - band or y >= h - band]
        white = sum(1 for c in edge if c == (255, 255, 255)) / max(1, len(edge))
        rows.append((white >= WHITE_EDGE_MIN, "主图边缘纯白 ≥99%", f"{white:.1%}"))
        box = product_bbox(rgb)
        fill = max(box[2] - box[0], box[3] - box[1]) / CANVAS if box else 0
        rows.append((fill >= MAIN_FILL_MIN, "主图产品占比 ≥85%（长边）", f"{fill:.0%}"))
        rows.append((not slot.get("headline") and not slot.get("points"), "主图无叠加文字"))
    else:
        words = listing_words(draft)
        texts = [slot.get("headline", "")] + slot.get("points", [])
        bad = [t for t in texts if "〔" in t or any(w not in words for w in re.findall(r"[a-z0-9]+", t.lower()))]
        rows.append((not bad, "叠加文字只用文案里已有的词、无〔待填〕", "；".join(bad)))
        banned = [t for t in texts if re.search(r"\bbest\b|#\s*1|guarantee|perfect|100\s*%", t, re.I)]
        rows.append((not banned, "叠加文字无违禁宣传语", "；".join(banned)))
    return rows


def cmd_check(run, quiet=False):
    p = paths(run)
    plan = load_json(p["plan"])
    draft = load_json(p["draft"], {})
    review = load_json(p["review"], {})
    _, concept = reference_images(p, plan)
    results, all_ok = {}, True
    for slot in plan["slots"]:
        sid = slot["id"]
        if slot.get("status") != "ready":
            results[sid] = {"status": "HOLD", "rows": [], "reason": slot.get("hold_reason", "")}
            continue
        path = os.path.join(p["final"], final_name(plan, slot, concept))
        preview = os.path.join(p["preview"], final_name(plan, slot, concept))
        if not os.path.exists(path) and os.path.exists(preview):
            # 新 clone：原图不入库，只有预览；沿用已提交的视觉质检，不重做像素检查
            v = review.get(sid, {})
            ok = str(v.get("verdict", "")).lower() == "pass"
            all_ok &= ok
            results[sid] = {"status": "PASS" if ok else "FAIL", "path": preview, "preview_only": True,
                            "rows": [(True, "原图未入库，使用已提交的 1000px 预览，未重做像素检查"),
                                     (ok, "视觉质检通过（沿用 review.json）", v.get("note", ""))]}
            continue
        if not os.path.exists(path):
            results[sid] = {"status": "FAIL", "rows": [(False, "成图存在", path)]}
            all_ok = False
            continue
        rows = check_slot(plan, slot, path, slot["mode"] == "compose_main", draft)
        v = review.get(sid)
        if not v:
            rows.append((False, "视觉质检已填（review.json）", "缺结论"))
        else:
            fails = [k for k, val in v.items() if k not in ("verdict", "note") and str(val).lower() != "pass"]
            rows.append((str(v.get("verdict", "")).lower() == "pass" and not fails, "视觉质检通过",
                         "；".join(fails) + (f"（{v.get('note')}）" if v.get("note") else "")))
        ok = all(r[0] for r in rows)
        all_ok &= ok
        results[sid] = {"status": "PASS" if ok else "FAIL", "rows": rows, "path": path}
    if not quiet:
        for sid, r in results.items():
            print(f"{r['status']:4}  {sid}" + (f"  —  {r.get('reason')}" if r["status"] == "HOLD" else ""))
            for ok, item, *detail in r["rows"]:
                if not ok:
                    print(f"        FAIL {item}" + (f"：{detail[0]}" if detail and detail[0] else ""))
    return results, all_ok


def cmd_render(run):
    p = paths(run)
    plan = load_json(p["plan"])
    _, concept = reference_images(p, plan)
    results, all_ok = cmd_check(run, quiet=True)
    os.makedirs(p["preview"], exist_ok=True)
    meta = load_json(p["draft"], {}).get("meta", {})
    lines = ["# S3 Listing · 图片", "",
             f"种子词：{meta.get('seed', '')}",
             f"站点：{meta.get('site', 'US')}",
             f"生成时间：{time.strftime('%Y-%m-%d %H:%M')}",
             "数据周期：沿用 s3_listing.md（图位依据取自其中的买家关心点与文案）",
             f"上游文件：{os.path.join(run, 's3_draft.json')}、{os.path.join(run, 'images_plan.json')}", "",
             f"针对候选：{plan.get('candidate', '')}",
             "出图：本机 Codex CLI 自带 image_gen；文字由 images.py 排版，模型不写字", ""]
    if concept:
        lines += ["> ⚠️ **本套图基于 AI 概念参考图生成（没有实拍图），只用于演示方案，不能直接上架。** "
                  "拿到实拍图后放进 `产品图/` 重跑。", ""]
    lines += ["## 图位", "", "| 图 | 图位 | 目的 | 依据 | 叠加文字 | 质检 |", "|---|---|---|---|---|---|"]
    for slot in plan["slots"]:
        r = results[slot["id"]]
        img_cell = "—"
        if r.get("path"):
            prev = os.path.join(p["preview"], os.path.basename(r["path"]))
            if not r.get("preview_only"):  # 只有原图在时才重新生成预览，避免反复压缩已提交的预览
                Image.open(r["path"]).resize((PREVIEW, PREVIEW), Image.LANCZOS).save(prev, "JPEG", quality=80, optimize=True)
            img_cell = f"![{slot['id']}](images/preview/{os.path.basename(prev)})"
        text = " / ".join(x for x in [slot.get("headline", "")] + slot.get("points", []) if x) or "无"
        status = r["status"] + (f"：{r.get('reason')}" if r["status"] == "HOLD" else "")
        lines.append(f"| {img_cell} | {slot['id']} | {slot.get('purpose', '')} | {slot.get('evidence', '')} | {text} | {status} |")
    holds = [s for s in plan["slots"] if s.get("status") != "ready"]
    lines += ["", "## 挂起（HOLD）与待补资料", ""]
    lines += [f"- [ ] {s['id']}：{s.get('hold_reason', '')}" for s in holds] or ["暂无"]
    lines += ["", "## 质检明细", ""]
    for sid, r in results.items():
        if not r["rows"]:
            continue
        lines.append(f"**{sid}**：{r['status']}")
        lines += [f"- {'✅' if ok else '❌'} {item}" + (f"（{d[0]}）" if d and d[0] else "") for ok, item, *d in r["rows"]]
        lines.append("")
    lines += ["结论：" + ("全部通过" if all_ok else "**有未通过项，见上**"), "", "---", "",
              "卖家精灵调用：新调用 0 次 / 读缓存 0 次（图片步骤不调用卖家精灵，出图走 Codex CLI）", ""]
    with open(p["md"], "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"已写出 {p['md']}")
    return 0 if all_ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["ref", "gen", "compose", "check", "render"])
    ap.add_argument("run")
    ap.add_argument("--only", nargs="*", help="gen 时只跑这些图位 id")
    a = ap.parse_args()
    if a.step == "ref":
        sys.exit(cmd_ref(a.run))
    if a.step == "gen":
        sys.exit(cmd_gen(a.run, a.only))
    if a.step == "compose":
        sys.exit(cmd_compose(a.run))
    if a.step == "check":
        sys.exit(0 if cmd_check(a.run)[1] else 1)
    sys.exit(cmd_render(a.run))


if __name__ == "__main__":
    main()
