"""
killmail.app 战斗报告截图模块

参照 killmail.app 截图方式：
垂直拼接多个视图区域的截图。
使用 Playwright 元素级截图 (element.screenshot)，避免 scroll+clip 的兼容性问题。

页面 DOM 结构（新版 killmail.app layout）：
  main
    ├── HEADER: .shrink-0.border-b.px-5.py-3.border-white\/5
    │     ├── 标题、系统名、击杀统计
    │     └── Tab 按钮: "Overview" "Pilots" "Composition"
    ├── SCROLL: .hidden.min-h-0.w-full.flex-col.items-center.overflow-auto.sm\\:flex
    │     └── CONTENT: .max-w-7xl.md\\:w-9\\/12
    │           ├── SCORE: .flex.items-start.gap-6
    │           │     ├── Overview: 3列（左队 + 中间对比 + 右队）
    │           │     ├── Pilots: 3列（同上，中间列重复需隐藏）
    │           │     └── Composition: 2列（无中间列）
    │           └── CHART: .flex.justify-center（仅 Overview 有内容）
    └── BOTTOM: .fixed.bottom-0.w-screen（速度控件 + 时间轴 canvas）
"""
import hashlib
from io import BytesIO

from nonebot import logger
from PIL import Image

from ..common.cache import cache as redis_cache

# 截图缓存时间（3 小时）
_SCREENSHOT_CACHE_TTL = 3 * 60 * 60

# 视口宽度（决定截图宽度）
_VIEWPORT_WIDTH = 1280
# 常规视口高度
_VIEWPORT_HEIGHT = 920
# 元素截图时最大视口高度
_MAX_SCREENSHOT_HEIGHT = 8000

# 内容裁切起始 x（内容 wrapper 左边界）
_CONTENT_LEFT = 209


async def html2pic_kmapp(url: str, viewport_width: int = _VIEWPORT_WIDTH) -> bytes:
    """
    截取 killmail.app 战斗报告并垂直拼合多个区域：

      1. 顶部标题 + 系统/统计信息
      2. Overview 比分详情
      3. Pilots 联盟飞行员分布（隐藏中间比较列）
      4. Composition 舰种构成
      5. 底部时间轴 canvas

    使用 element.screenshot() 直接截取每个元素的完整内容。

    Args:
        url: killmail.app 战斗报告 URL
        viewport_width: 视口宽度，默认 1280

    Returns:
        PNG 二进制数据
    """
    from nonebot_plugin_htmlrender import get_new_page

    # ── 缓存 ──────────────────────────────────────────────────
    cache_key = f"render:kmapp:{hashlib.md5(f'{url}|{viewport_width}'.encode()).hexdigest()}"
    cached = await redis_cache.get(cache_key)
    if cached is not None:
        return cached

    async with get_new_page(
        viewport={"width": viewport_width, "height": _VIEWPORT_HEIGHT},
        device_scale_factor=1,
    ) as page:
        await page.goto(url)
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(1500)

        # ── 辅助函数 ──────────────────────────────────────────

        async def _click_tab(text: str) -> None:
            """通过文本点击 Tab 按钮。"""
            await page.evaluate(
                """(t) => {
                    const btn = Array.from(document.querySelectorAll('button'))
                        .find(b => b.textContent?.trim() === t
                            && b.getBoundingClientRect().width > 0);
                    btn?.click();
                }""",
                text,
            )
            await page.wait_for_timeout(800)

        async def _expand_scroll() -> None:
            """解除滚动容器的溢出限制，使内容可完整渲染。"""
            await page.evaluate("""() => {
                const sc = document.querySelector('[class*="overflow-auto"]');
                if (sc) {
                    sc.style.overflow = 'visible';
                    sc.style.height = 'auto';
                    sc.style.maxHeight = 'none';
                }
            }""")
            await page.wait_for_timeout(400)

        async def _hide_bottom_bar() -> None:
            """隐藏底部固定栏（速度控件 + 时间轴），避免遮挡内容。"""
            await page.evaluate("""() => {
                const bar = document.querySelector('.fixed.bottom-0.w-screen');
                if (bar) bar.style.display = 'none';
            }""")
            await page.wait_for_timeout(200)

        async def _hide_center_column() -> None:
            """隐藏中间比较列（Pilots 视图中与 Overview 重复的列）。"""
            await page.evaluate("""() => {
                const score = document.querySelector('.flex.items-start.gap-6');
                if (score && score.children.length >= 3) {
                    score.children[1].style.display = 'none';
                }
            }""")
            await page.wait_for_timeout(200)

        async def _shoot_element(selector: str, label: str = "", crop_x: int | None = None, crop_w: int | None = None) -> bytes | None:
            """通用 element.screenshot，自适应视口高度，支持水平裁切。"""
            el = await page.query_selector(selector)
            if el is None:
                logger.debug(f"html2pic_kmapp: 未找到 {selector}")
                return None
            scroll_h = await el.evaluate("e => e.scrollHeight")
            if scroll_h < 10:
                return None
            vp_w = await page.evaluate("() => window.innerWidth")
            target_h = min(scroll_h + 200, _MAX_SCREENSHOT_HEIGHT)
            await page.set_viewport_size({"width": vp_w, "height": target_h})
            await page.wait_for_timeout(300)
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(300)
            logger.debug(
                f"html2pic_kmapp: {label or selector} "
                f"scrollHeight={scroll_h}, viewport={vp_w}x{target_h}"
            )
            png = await el.screenshot()

            if crop_x is not None and crop_w is not None:
                img = Image.open(BytesIO(png)).convert("RGB")
                img_cropped = img.crop((crop_x, 0, crop_x + crop_w, img.height))
                buf = BytesIO()
                img_cropped.save(buf, format="PNG")
                png = buf.getvalue()
                logger.debug(
                    f"html2pic_kmapp: {label or selector} 裁切后 "
                    f"x={crop_x}, w={crop_w}, h={img.height}"
                )

            return png

        # ── 先计算内容区域裁切坐标（统一用于所有部分）─────────
        await _hide_bottom_bar()

        crop_left, crop_width = await page.evaluate("""
            () => {
                const wrapper = document.querySelector('[class*="max-w-7xl"]');
                if (!wrapper) return [0, window.innerWidth];
                const r = wrapper.getBoundingClientRect();
                return [Math.round(r.x), Math.round(r.width)];
            }
        """)

        # ── Part 1: 顶部标题栏 ────────────────────────────────
        title_png = await _shoot_element(
            ".shrink-0.border-b.px-5.py-3.border-white\\/5",
            "header",
            crop_x=crop_left, crop_w=crop_width,
        )

        # ── Part 2: Overview（分数概览 + 击杀图表）────────────
        await _click_tab("Overview")
        await _expand_scroll()

        overview_png = await _shoot_element(
            "[class*='max-w-7xl']",
            "overview",
            crop_x=crop_left, crop_w=crop_width,
        )

        # ── Part 3: Pilots（隐藏中间对比列）───────────────────
        await _click_tab("Pilots")
        await _hide_center_column()
        await _expand_scroll()

        pilots_png = await _shoot_element(
            "[class*='max-w-7xl']",
            "pilots",
            crop_x=crop_left, crop_w=crop_width,
        )

        # ── Part 4: Composition（无中间列，直接截图）──────────
        await _click_tab("Composition")
        await _expand_scroll()

        comp_png = await _shoot_element(
            "[class*='max-w-7xl']",
            "composition",
            crop_x=crop_left, crop_w=crop_width,
        )

        # ── Part 5: 底部时间轴 canvas ────────────────────────
        # 恢复底部栏显示，隐藏速度控件
        await page.evaluate("""() => {
            const bar = document.querySelector('.fixed.bottom-0.w-screen');
            if (bar) {
                bar.style.display = '';
                const ctrl = bar.querySelector('[class*="mb-3"]');
                if (ctrl) ctrl.style.display = 'none';
            }
        }""")
        await page.wait_for_timeout(300)

        bottom_png: bytes | None = None
        canvas_el = await page.query_selector("canvas")
        if canvas_el:
            box = await canvas_el.bounding_box()
            if box and box["height"] > 10:
                vp_w = await page.evaluate("() => window.innerWidth")
                await page.set_viewport_size({
                    "width": vp_w,
                    "height": min(int(box["height"]) + 200, _MAX_SCREENSHOT_HEIGHT),
                })
                await page.wait_for_timeout(300)
                bottom_png = await canvas_el.screenshot()
                logger.debug(
                    f"html2pic_kmapp: canvas 截图完成 "
                    f"({box['width']:.0f}x{box['height']:.0f})"
                )

        # ── 垂直拼接 ──────────────────────────────────────────
        parts: list[Image.Image] = []
        for png_data in [title_png, overview_png, pilots_png, comp_png]:
            if png_data:
                parts.append(Image.open(BytesIO(png_data)).convert("RGB"))

        if bottom_png:
            parts.append(Image.open(BytesIO(bottom_png)).convert("RGB"))

        if not parts:
            raise ValueError("未截取到任何内容")

        canvas_w = max(img.width for img in parts)
        canvas_h = sum(img.height for img in parts)
        canvas = Image.new("RGB", (canvas_w, canvas_h), (6, 8, 12))
        y_off = 0
        for img in parts:
            canvas.paste(img, (0, y_off))
            y_off += img.height

        buf = BytesIO()
        canvas.save(buf, format="PNG")
        result = buf.getvalue()

    await redis_cache.set(cache_key, result, _SCREENSHOT_CACHE_TTL)
    logger.debug(
        f"html2pic_kmapp: 全部截图完成，总高度={canvas_h}px"
    )
    return result
