"""
WarBeacon 战斗报告截图模块

参照 killmail.app (html2pic_kmapp) 的截图方式：
垂直拼接多个视图区域的截图。
使用 Playwright 元素级截图 (element.screenshot)，避免 scroll+clip 的兼容性问题。

页面 DOM 结构（Tab 专属容器内）：
  └── .battle-report-involved.view-xxx
        ├── .br-layout-row
        │     └── .br-main-content
        │           └── .n-space > div >
        │                 ├── .banner-outer     ← 顶部统计（所有 Tab 相同，仅截图一次）
        │                 └── div > .compact-teams ← Tab 专属主体（各 Tab 不同）
        └── .brf-chart-dock  ← 底部 ISK 图表（所有 Tab 相同，仅截图一次）
"""
import hashlib
from io import BytesIO

from nonebot import logger
from PIL import Image

from . import _SCREENSHOT_CACHE_TTL
from ..common.cache import cache as redis_cache

# 需要截图的 Tab 视图（名称 → URL hash 映射，语言无关）
_VIEWS: list[tuple[str, str]] = [
    ("Overview", "overview"),
    ("Participants", "involved"),
    ("Composition", "composition"),
]

# 视口宽度（决定截图宽度）
_VIEWPORT_WIDTH = 1920
# 常规视口高度
_VIEWPORT_HEIGHT = 920
# 元素截图时最大视口高度（防止内存溢出）
_MAX_SCREENSHOT_HEIGHT = 8000

# 默认视口宽度下限（可能被缩放，以此为基准计算裁切比例）
_REFERENCE_PAGE_WIDTH = 1680


async def html2pic_warbeacon(
    url: str,
    viewport_width: int = _VIEWPORT_WIDTH,
) -> bytes:
    """
    WarBeacon 战斗报告截图，参照 killmail.app 方式垂直拼接多个区域：

      1. 顶部统计 banner（仅截图一次）
      2. Overview 总览 —— 队伍卡片、基本统计
      3. Participants 参战人员 —— 各军团/联盟飞行员详情
      4. Composition 舰船构成 —— 按 Hull 分类的舰船统计
      5. 底部 ISK 损失图表（仅最后拼接一次）

    使用 element.screenshot() 直接截取每个元素的完整内容。

    Args:
        url: warbeacon.net 战斗报告 URL（如 https://warbeacon.net/br/report/xxx）
        viewport_width: 视口宽度，默认 1920

    Returns:
        PNG 二进制数据
    """
    from nonebot_plugin_htmlrender import get_new_page

    # ── 缓存 ──────────────────────────────────────────────────
    cache_key = f"render:warbeacon:{hashlib.md5(f'{url}|{viewport_width}'.encode()).hexdigest()}"
    cached = await redis_cache.get(cache_key)
    if cached is not None:
        return cached

    async with get_new_page(
        viewport={"width": viewport_width, "height": _VIEWPORT_HEIGHT},
        device_scale_factor=1,
    ) as page:
        # ── 导航并设置语言 ───────────────────────────────────
        await page.goto(url)
        await page.wait_for_load_state("networkidle")

        await page.evaluate("""
            localStorage.setItem('eve-warbeacon-locale', 'zh');
            localStorage.setItem('hideDragDropTip', 'true');
        """)
        await page.reload()
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(1000)

        # ── 辅助函数：通过 URL hash 切换 Tab（语言无关）──────
        async def _switch_tab(hash: str) -> None:
            """通过设置 location.hash 切换 Tab 视图，不依赖按钮文字。"""
            await page.evaluate(f"window.location.hash = '#{hash}'")
            await page.wait_for_timeout(800)
            await page.wait_for_load_state("networkidle")

        # ── 展开内容容器 + 隐藏 kill feed / chart-dock ────────
        async def _expand_and_hide(hide_team_headers: bool = False) -> None:
            """展开所有内容容器，隐藏右侧 kill feed 和底部图表。"""
            await page.evaluate("""
                (hideHeaders) => {
                    const kf = document.querySelector('.brf-kf-root');
                    if (kf) kf.style.display = 'none';
                    const chart = document.querySelector('.brf-chart-dock');
                    if (chart) chart.style.display = 'none';
                    // 隐藏 Tab 内容中的搜索框
                    const filters = document.querySelectorAll('.detail-filter-input');
                    filters.forEach(f => f.style.display = 'none');
                    // 对后续截图隐藏队伍头部统计（已在 Overview 中展示过）
                    if (hideHeaders) {
                        const heads = document.querySelectorAll('.brf-tc-head');
                        heads.forEach(h => h.style.display = 'none');
                    }
                    const containers = [
                        '.compact-teams', '.battle-report-involved',
                        '.br-layout-row', '.br-main-content',
                        '.compact-team-card', '.battle-report-container',
                    ];
                    document.querySelectorAll(containers.join(',')).forEach(el => {
                        el.style.setProperty('height', 'auto', 'important');
                        el.style.setProperty('max-height', 'none', 'important');
                        el.style.setProperty('overflow', 'visible', 'important');
                    });
                }
            """, hide_team_headers)
            await page.wait_for_timeout(400)

        # ── 等待图片加载 ──────────────────────────────────────
        async def _wait_for_images() -> None:
            await page.evaluate("""
                () => new Promise((resolve) => {
                    const check = () => {
                        const imgs = Array.from(document.querySelectorAll('img'))
                            .filter(img => {
                                const r = img.getBoundingClientRect();
                                return r.top < window.innerHeight && r.bottom > 0;
                            });
                        if (imgs.length === 0 || imgs.every(
                            i => i.complete && i.naturalWidth > 0)
                        ) { resolve(); }
                        else { setTimeout(check, 200); }
                    };
                    check();
                    setTimeout(resolve, 8000);
                })
            """)

        # ── 辅助函数：element.screenshot 封装 ─────────────────
        async def _shoot_element(selector: str, label: str = "", crop_x: int | None = None, crop_w: int | None = None) -> bytes | None:
            """通用 element.screenshot，自动设置视口高度以适应内容。
            
            可选择对截图结果进行水平裁切（去除左右空白）。
            
            Args:
                selector: 元素 CSS 选择器
                label: 日志标签
                crop_x: 裁切起始 x 坐标（页面 CSS px），None 表示不裁切
                crop_w: 裁切宽度，None 表示不裁切
            """
            el = await page.query_selector(selector)
            if el is None:
                logger.debug(f"html2pic_warbeacon: 未找到 {selector}")
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
                f"html2pic_warbeacon: {label or selector} "
                f"scrollHeight={scroll_h}, viewport={vp_w}x{target_h}"
            )
            png = await el.screenshot()
            
            if crop_x is not None and crop_w is not None:
                img = Image.open(BytesIO(png)).convert("RGB")
                # 裁切区域：crop_x 到 crop_x + crop_w，全高度
                img_cropped = img.crop((crop_x, 0, crop_x + crop_w, img.height))
                buf = BytesIO()
                img_cropped.save(buf, format="PNG")
                png = buf.getvalue()
                logger.debug(
                    f"html2pic_warbeacon: {label or selector} 裁切后 "
                    f"x={crop_x}, w={crop_w}, h={img.height}"
                )
            
            return png

        # ── 先计算队伍卡片的实际内容区域（统一用于所有部分裁切）─
        await _switch_tab("overview")
        await _expand_and_hide()
        await _wait_for_images()

        crop_left, crop_width = await page.evaluate("""
            () => {
                const cards = document.querySelectorAll('.compact-team-card');
                let minX = Infinity, maxX = -Infinity;
                cards.forEach(c => {
                    const r = c.getBoundingClientRect();
                    if (r.x < minX) minX = r.x;
                    if (r.x + r.width > maxX) maxX = r.x + r.width;
                });
                const gaps = document.querySelectorAll('.team-insert-gap');
                gaps.forEach(g => {
                    const r = g.getBoundingClientRect();
                    if (r.x + r.width > maxX) maxX = r.x + r.width;
                });
                return [Math.round(minX), Math.round(maxX - minX)];
            }
        """)

        parts: list[Image.Image] = []

        # ── Part 1: 顶部统计 banner（仅截图一次）───────────────
        banner_png = await _shoot_element(".banner-outer", "banner-outer",
                                          crop_x=crop_left, crop_w=crop_width)
        if banner_png:
            parts.append(Image.open(BytesIO(banner_png)).convert("RGB"))

        # ── Part 2~4: 逐 Tab 截图专属主体（.compact-teams）───
        for idx, (tab_text, tab_hash) in enumerate(_VIEWS):
            logger.debug(f"html2pic_warbeacon: 正在截图 {tab_text} ({idx+1}/{len(_VIEWS)})...")

            if idx > 0:
                await _switch_tab(tab_hash)
                # 后续 Tab 隐藏队伍头部统计（已在 Overview 中展示过）
                await _expand_and_hide(hide_team_headers=True)
                await _wait_for_images()

            teams_png = await _shoot_element(".compact-teams", f"{tab_text}.compact-teams",
                                                crop_x=crop_left, crop_w=crop_width)
            if teams_png:
                parts.append(Image.open(BytesIO(teams_png)).convert("RGB"))
                logger.debug(f"html2pic_warbeacon: {tab_text} 截图完成（crop: {crop_left}x{crop_width}）")

        # ── Part 5: 底部 chart-dock（仅截图一次）──────────────
        await page.evaluate("""() => {
            const c = document.querySelector('.brf-chart-dock');
            if (c) {
                c.style.display = '';
                c.style.setProperty('height', 'auto', 'important');
                c.style.setProperty('overflow', 'visible', 'important');
            }
        }""")
        await page.wait_for_timeout(300)

        chart_png = await _shoot_element(".brf-chart-dock", "chart-dock",
                                          crop_x=crop_left, crop_w=crop_width)
        if chart_png:
            parts.append(Image.open(BytesIO(chart_png)).convert("RGB"))
            logger.debug(f"html2pic_warbeacon: chart-dock 截图完成（crop: {crop_left}x{crop_width}）")

        # ── 垂直拼接 ──────────────────────────────────────────
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
    logger.debug(f"html2pic_warbeacon: 全部截图完成，总高度={canvas_h}px")
    return result
