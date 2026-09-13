"""按口播稿逐句操作工作台，用 CDP screencast 抓高清帧，并记录每句的开始时间。

输出：frames/*.jpg、frames.txt（ffmpeg concat 清单）、timeline.json（每句在视频中的开始秒数）。
"""
import asyncio, base64, json, os, time
from playwright.async_api import async_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
WB = "file://" + os.path.abspath(os.path.join(HERE, "..", "index.html"))  # 仓库里的 workbench/index.html
COVER = "file://" + os.path.join(HERE, "cover.html")
ENDING = "file://" + os.path.join(HERE, "ending.html")
DUR = json.load(open(os.path.join(HERE, "durations.json")))
ORDER = [lid for lid, _ in json.load(open(os.path.join(HERE, "lines.json")))]
GAP = 0.45            # 句间停顿
LEAD = 1.2            # 片头静默
TAIL = 2.0            # 片尾静默
VW, VH, DSF = 1536, 864, 1.25   # 输出 1920×1080

INIT = r"""
(() => {
  const css = `#fc{position:fixed;z-index:2147483647;width:26px;height:26px;margin:-4px 0 0 -4px;pointer-events:none;
     background:url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="26" height="26"><path d="M3 2l18 10-8 2-4 8z" fill="%23ffffff" stroke="%23000" stroke-width="1.6" stroke-linejoin="round"/></svg>') no-repeat;
     transition:transform .12s}
   #fc.down{transform:scale(.8)}
   #tt{position:fixed;z-index:2147483646;max-width:460px;background:#1b2437;color:#fff;font:13px/1.5 -apple-system,"PingFang SC",sans-serif;
     padding:8px 11px;border-radius:8px;box-shadow:0 6px 18px rgba(0,0,0,.25);pointer-events:none;display:none}
   .spot{outline:3px solid #ff9a3c !important;outline-offset:3px;border-radius:6px;transition:outline .2s}`;
  const add = () => {
    if (document.getElementById('fc')) return;
    const s = document.createElement('style'); s.textContent = css; document.head.appendChild(s);
    const c = document.createElement('div'); c.id = 'fc'; document.body.appendChild(c);
    const t = document.createElement('div'); t.id = 'tt'; document.body.appendChild(t);
    c.style.left = (window.__mx || innerWidth / 2) + 'px'; c.style.top = (window.__my || innerHeight / 2) + 'px';
  };
  document.addEventListener('DOMContentLoaded', add);
  document.addEventListener('mousemove', e => {
    add(); window.__mx = e.clientX; window.__my = e.clientY;
    const c = document.getElementById('fc'); c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px';
    const tt = document.getElementById('tt'); const el = e.target.closest && e.target.closest('[title],[data-tt]');
    if (el) {
      if (el.hasAttribute('title')) { el.dataset.tt = el.getAttribute('title'); el.removeAttribute('title'); }
      tt.textContent = el.dataset.tt; tt.style.display = 'block';
      tt.style.left = Math.min(e.clientX + 16, innerWidth - 480) + 'px'; tt.style.top = (e.clientY + 22) + 'px';
    } else tt.style.display = 'none';
  }, true);
  document.addEventListener('mousedown', () => { const c = document.getElementById('fc'); c && c.classList.add('down'); }, true);
  document.addEventListener('mouseup', () => { const c = document.getElementById('fc'); c && c.classList.remove('down'); }, true);
})();
"""


async def main():
    os.makedirs(os.path.join(HERE, "frames"), exist_ok=True)
    for f in os.listdir(os.path.join(HERE, "frames")):
        os.remove(os.path.join(HERE, "frames", f))
    frames = []  # (path, wallclock)

    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True)  # 用本机已装的 Google Chrome
        ctx = await browser.new_context(viewport={"width": VW, "height": VH}, device_scale_factor=DSF)
        await ctx.add_init_script(INIT)
        page = await ctx.new_page()
        page.set_default_timeout(4000)  # 单个动作出错最多卡 4 秒，不拖垮后面的对齐
        cdp = await ctx.new_cdp_session(page)

        async def on_frame(ev):
            path = os.path.join(HERE, "frames", f"{len(frames):06d}.jpg")
            with open(path, "wb") as fh:
                fh.write(base64.b64decode(ev["data"]))
            frames.append((path, time.monotonic()))
            try:
                await cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})
            except Exception:
                pass

        cdp.on("Page.screencastFrame", lambda ev: asyncio.ensure_future(on_frame(ev)))
        m = page.mouse
        mouse = {"x": VW / 2, "y": VH / 2}

        async def move_to(sel, nth=0, steps=18, dx=0.5, dy=0.5):
            loc = page.locator(sel).nth(nth)
            await loc.scroll_into_view_if_needed()
            box = await loc.bounding_box()
            if not box:
                return
            x, y = box["x"] + box["width"] * dx, box["y"] + box["height"] * dy
            await m.move(x, y, steps=steps)
            mouse["x"], mouse["y"] = x, y

        async def click(sel, nth=0):
            # 只做一次真实鼠标点击；再调 locator.click 会连点两下，把关键词高亮切回去
            await move_to(sel, nth)
            await m.down(); await asyncio.sleep(0.08); await m.up()

        async def nav(hash_):
            await click(f'nav a[href="#{hash_}"]')
            await asyncio.sleep(0.5)

        async def smooth_scroll(sel, nth=0, block="center"):
            await page.locator(sel).nth(nth).evaluate(f"e => e.scrollIntoView({{behavior:'smooth', block:'{block}'}})")
            await asyncio.sleep(0.9)

        async def wiggle():
            await m.move(mouse["x"] + 3, mouse["y"] + 2, steps=3)

        # ---------- 每句开始时执行的动作 ----------
        async def a_s1a():
            await asyncio.sleep(0.1)
        async def a_s2a():
            await page.goto(WB); await page.wait_for_load_state("load")
            await m.move(VW * 0.6, VH * 0.6, steps=1)
            await move_to("#q", dx=0.12, steps=25)
            await asyncio.sleep(1.0); await move_to("#q", dx=0.45, steps=40)
        async def a_s2b():
            await click("#go")
        async def a_s2c():
            await smooth_scroll(".trace")
            nodes = await page.locator(".trace .node").count()
            per = max(0.6, (DUR["s2c"] - 1.5) / max(nodes, 1))
            for i in range(nodes):
                await move_to(".trace .node", i, steps=20); await asyncio.sleep(per - 0.3)
        async def a_s3a():
            await nav("s1"); await move_to("table tr:nth-child(2) td:nth-child(1)")
        async def a_s3b():
            await move_to("table tr:nth-child(2) td:nth-child(3)", steps=25)
        async def a_s3c():
            await move_to("table tr:nth-child(4) td:nth-child(3)", steps=25)
        async def a_s3d():
            await smooth_scroll(".cand.sel")
            await move_to(".cand.sel .num", 1, steps=22); await asyncio.sleep(DUR["s3d"] * 0.35)
            await move_to(".cand.sel div:last-child", steps=22)
        async def a_s3e():
            await smooth_scroll(".callout"); await move_to(".callout", steps=22, dx=0.3)
        async def a_s3f():
            await page.evaluate("window.scrollTo({top:0, behavior:'smooth'})")
            await move_to("h1", steps=30, dx=0.2)
        async def a_s4a():
            await nav("s2"); await move_to(".cand.sel .num", steps=22)
        async def a_s4b():
            await move_to(".cand .verdict", 0, steps=22)
        async def a_s4c():
            await smooth_scroll(".callout"); await move_to(".callout b", steps=22)
            await asyncio.sleep(DUR["s4c"] * 0.5); await move_to(".callout code", steps=22)
        async def a_s5a():
            await nav("s3")
            await move_to("table tr:nth-child(2) td:nth-child(1)", steps=22); await asyncio.sleep(DUR["s5a"] * 0.45)
            await move_to("ol.bul li", 0, steps=22)
        async def a_s5b():
            await move_to("ol.bul li", 2, steps=22)
        async def a_s5c():
            await move_to(".listing-title", steps=22, dx=0.55, dy=0.75)
        async def a_s5d():
            await move_to(".kw", 3, steps=22); await wiggle()
            await asyncio.sleep(DUR["s5d"] * 0.5); await move_to(".kw", 6, steps=12); await wiggle()
        async def a_s5e():
            await page.evaluate("window.scrollTo({top:0, behavior:'smooth'})"); await asyncio.sleep(0.5)
            await move_to("h1 .pill.g", steps=22)
        async def a_s5f():
            await smooth_scroll(".imgs"); await move_to(".imgs figure", 0, steps=20)
            await asyncio.sleep(DUR["s5f"] * 0.25); await move_to(".imgs .hold", steps=25)
        async def a_s6a():
            await nav("s4"); await move_to(".bar", steps=22, dx=0.1)
            await m.move(mouse["x"] + 700, mouse["y"], steps=40)
            for i in range(3):
                await move_to(".adcol h3", i, steps=20); await asyncio.sleep(0.5)
        async def a_s6b():
            loc = page.locator(".ad", has_text="utensil organizer for kitchen drawers").locator(".src").first
            await loc.evaluate("e => e.scrollIntoView({behavior:'smooth', block:'center'})")
            await asyncio.sleep(1.0)
            box = await loc.bounding_box()
            await m.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=25)
            mouse["x"], mouse["y"] = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        async def a_s6c():
            await page.evaluate("window.scrollTo({top:0, behavior:'smooth'})"); await asyncio.sleep(0.4)
            await click('.adcol .kw[data-kw="expandable bamboo drawer organizer"]'); await asyncio.sleep(1.2)
            await nav("s1"); await move_to('.kw.hl', 0, steps=20); await asyncio.sleep(1.6)
            await nav("s3"); await move_to('.card .kw.hl', 0, steps=20)
        async def a_s6d():
            await nav("s4"); await smooth_scroll(".grid2 table")
            await move_to(".grid2 table tr", 0, steps=25, dx=0.3)
        async def a_s7a():
            await move_to("#sidefoot", steps=30, dx=0.4, dy=0.8)
        async def a_s7b():
            await page.goto(ENDING); await page.wait_for_load_state("load")
            await page.evaluate("window.startScroll()")
        async def a_s7c():
            await page.evaluate("window.showBig()")

        actions = {k[2:]: v for k, v in locals().items() if k.startswith("a_s")}

        # ---------- 开录 ----------
        await page.goto(COVER); await page.wait_for_load_state("load")
        await cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "maxWidth": 1920, "maxHeight": 1080, "everyNthFrame": 1})
        t0 = time.monotonic()
        await asyncio.sleep(LEAD)
        timeline, cursor = {}, LEAD
        for lid in ORDER:
            target = t0 + cursor
            await asyncio.sleep(max(0, target - time.monotonic()))
            timeline[lid] = round(time.monotonic() - t0, 3)
            if lid in actions:
                try:
                    await actions[lid]()
                except Exception as e:
                    print("action error", lid, repr(e)[:160])
            cursor += DUR[lid] + GAP
            # 画面不动时 screencast 不出帧：轻微移动鼠标保证帧连续
            while time.monotonic() < t0 + cursor - 0.05:
                await m.move(mouse["x"] + 0.5, mouse["y"], steps=1); await m.move(mouse["x"], mouse["y"], steps=1)
                await asyncio.sleep(0.25)
        await asyncio.sleep(TAIL)
        end = time.monotonic()
        await cdp.send("Page.stopScreencast")
        await asyncio.sleep(0.5)
        await browser.close()

    # concat 清单：每帧持续到下一帧
    with open(os.path.join(HERE, "frames.txt"), "w") as fh:
        for i, (path, t) in enumerate(frames):
            nxt = frames[i + 1][1] if i + 1 < len(frames) else end
            start = max(t, t0)
            fh.write(f"file '{path}'\nduration {max(0.001, nxt - start):.4f}\n")
        fh.write(f"file '{frames[-1][0]}'\n")
    first = frames[0][1] - t0 if frames else 0
    json.dump({"timeline": timeline, "first_frame_offset": first, "total": end - t0, "frames": len(frames)},
              open(os.path.join(HERE, "timeline.json"), "w"), indent=1)
    print("frames", len(frames), "total %.1fs" % (end - t0), "first_frame_offset %.3f" % first)


asyncio.run(main())
