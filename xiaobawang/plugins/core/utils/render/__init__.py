import asyncio
from io import BytesIO
from pathlib import Path
from typing import Any

from nonebot import logger, require
from PIL import Image

from ...config import SRC_PATH
from .utils import (
    expand_scrollable_containers,
    get_element_dimensions,
    get_teams_count,
    scroll_and_load_all_content,
    wait_for_all_images_in_viewport,
)

require("nonebot_plugin_htmlrender")

from nonebot_plugin_htmlrender import get_new_page, template_to_pic

# 定义模板路径
templates_path = SRC_PATH / "templates"


async def capture_element(
    url: str | None = None,
    html_content: str | None = None,
    element: str = "body",
    hide_elements: list[str] | None = None,
    viewport_width: int = 1920,
    viewport_height: int = 1080,
    full_page: bool = False,
) -> bytes:
    """
    通用网页元素截图函数

    Args:
        url: 要截图的网页URL
        html_content: HTML内容字符串
        element: 要截图的元素选择器
        hide_elements: 需要隐藏的元素列表
        viewport_width: 视口宽度
        viewport_height: 视口高度
        full_page: 是否需要完整页面滚动截图

    Returns:
        图片二进制数据
    """
    async with get_new_page(
        viewport={"width": viewport_width, "height": viewport_height}, device_scale_factor=1
    ) as page:
        if url:
            await page.goto(url)
            await page.wait_for_load_state("networkidle")
        elif html_content:
            await page.set_content(html_content)
        else:
            raise ValueError("必须提供 url 或 html_content 其中之一")

        if hide_elements:
            await page.evaluate(
                """
                (selectors) => {
                    selectors.forEach(selector => {
                        const elements = document.querySelectorAll(selector);
                        elements.forEach(element => {
                            element.style.display = 'none';
                        });
                    });
                }
            """,
                hide_elements,
            )

        element_handle = await page.wait_for_selector(element)
        if element_handle is None:
            raise ValueError(f"未找到元素 '{element}'")

        bounding_box = await element_handle.bounding_box()
        if not bounding_box:
            raise ValueError(f"无法获取元素 '{element}' 的边界框")

        element_width = bounding_box["width"]
        element_height = bounding_box["height"]

        if full_page:
            screenshots = []
            viewport_height = min(viewport_height, 1080)

            for offset in range(0, int(element_height), viewport_height):
                await page.evaluate(f"window.scrollTo(0, {offset})")
                await page.wait_for_timeout(500)

                screenshot = await page.screenshot(
                    clip={
                        "x": bounding_box["x"],
                        "y": bounding_box["y"] - offset if bounding_box["y"] > offset else 0,
                        "width": element_width,
                        "height": min(viewport_height, element_height - offset),
                    }
                )
                screenshots.append(screenshot)

            stitched_image = Image.new("RGB", (int(element_width), int(element_height)))
            current_height = 0
            for screenshot in screenshots:
                img = Image.open(BytesIO(screenshot))
                stitched_image.paste(img, (0, current_height))
                current_height += img.height
        else:
            await page.set_viewport_size({"width": int(viewport_width), "height": int(element_height)})
            await page.wait_for_load_state("networkidle")

            # 截图整个元素
            screenshot = await page.screenshot(
                clip={"x": bounding_box["x"], "y": bounding_box["y"], "width": element_width, "height": element_height}
            )

        return screenshot


async def render_template(
    template_path: Path,
    template_name: str,
    data: dict[str, Any] | Any,
    width: int = 550,
    height: int = 10,
) -> bytes | str:
    """通用模板渲染函数"""
    return await template_to_pic(
        template_path=str(template_path),
        template_name=template_name,
        templates=data,
        pages={
            "viewport": {"width": width, "height": height},
            "base_url": f"file://{template_path}",
        },
    )


async def html2pic_br(
    html_content: str | None = None,
    url: str | None = None,
    element: str | None = None,
    hide_elements: list | None = None,
    trim_class: str = "hOohQec_",
    click_selector: str | None = None,
) -> bytes | str:
    """
    BR网页元素截图函数
    :param html_content:
    :param url: br链接
    :param element: 需要截图的元素
    :param hide_elements: 需要隐藏的元素
    :param trim_class: 间隔统计元素
    :param click_selector: 选择需要点击的元素 bp3-tab-panel_general_ [involved,summary,timeline,damage,composition]
    :return:
    """
    async with get_new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1) as page:
        if url:
            await page.goto(url)
            await page.wait_for_load_state("networkidle")
        else:
            await page.set_content(html_content)

        if hide_elements:
            await page.evaluate(
                """
                (selectors) => {
                    selectors.forEach(selector => {
                        const elements = document.querySelectorAll(selector);
                        elements.forEach(element => {
                            element.style.display = 'none';
                        });
                    });
                }
            """,
                hide_elements,
            )

        trim_width = 0
        if trim_class:
            trim_element = await page.query_selector(f".{trim_class}")
            if trim_element:
                trim_box = await trim_element.bounding_box()
                if trim_box:
                    trim_width = trim_box["width"] * 0.9
        logger.debug(f"trim_width: {trim_width}")
        element_handle = await page.wait_for_selector(element)
        if element_handle is None:
            raise ValueError(f"Element '{element}' not found on the page.")

        bounding_box = await element_handle.bounding_box()
        element_width = bounding_box["width"]
        element_height = bounding_box["height"]

        await page.set_viewport_size({"width": int(element_width), "height": min(3000, int(element_height))})

        await page.wait_for_load_state("networkidle")

        if click_selector:
            try:
                click_element = await page.wait_for_selector(f'[data-tab-id="{click_selector}"]', timeout=1000)
                if click_element:
                    await click_element.click()
                    await page.wait_for_timeout(1000)
                    await page.wait_for_load_state("networkidle")
            except Exception as e:
                logger.error(f"点击元素 '{click_selector}' 失败: {e!s}")

        clip_width = element_width
        clip_x = bounding_box["x"]
        if trim_width and trim_width * 2 < element_width:
            clip_width = element_width - trim_width * 2
            clip_x = bounding_box["x"] + trim_width

        screenshot = await page.screenshot(
            clip={"x": clip_x, "y": bounding_box["y"], "width": clip_width, "height": element_height}
        )

        return screenshot


async def html2pic_war_beacon(
    url: str,
    click_text: str | None = None,
    element_class: str = "compact-teams",
) -> bytes:
    """
    截图战争信标(War Beacon)网页的特定元素，支持懒加载和虚拟滚动

    Args:
        url: 要截图的网页URL
        click_text: 需要点击的文本内容
        element_class: 要截图的主要元素类名

    Returns:
        bytes: 截图的二进制数据
    """
    if not url:
        raise ValueError("必须提供URL")

    async with get_new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1) as page:
        # 配置页面
        await page.route("**/*", lambda route: route.continue_())
        await page.goto(url)

        # 设置本地存储以改变语言和隐藏提示
        await page.evaluate("""
            localStorage.setItem('eve-warbeacon-locale', 'zh');
            localStorage.setItem('hideDragDropTip', 'true');
        """)

        # 重新加载页面以应用设置
        await page.reload()
        await page.wait_for_load_state("networkidle")

        # 滚动加载所有内容
        await scroll_and_load_all_content(page)

        # 如果需要点击特定文本
        if click_text:
            try:
                element_with_text = await page.wait_for_selector(f"text='{click_text}'", timeout=2000)
                if element_with_text:
                    await element_with_text.click()
                    await page.wait_for_timeout(1000)
                    await page.wait_for_load_state("networkidle")
                    await scroll_and_load_all_content(page)
            except Exception as e:
                logger.error(f"点击文字 '{click_text}' 失败: {e!s}")

        # 获取队伍数量
        count = await get_teams_count(page)

        # 获取主元素和捕获元素的尺寸
        main_element_box = await get_element_dimensions(page, f".{element_class}")
        if not main_element_box:
            raise ValueError(f"未找到元素 '.{element_class}'")

        element_handle = await page.wait_for_selector(f".{element_class}")
        if element_handle:
            await element_handle.scroll_into_view_if_needed()

        # 等待图片加载
        await wait_for_all_images_in_viewport(page)
        await page.wait_for_timeout(500)

        # 获取捕获元素的尺寸
        capture_class = ".battle-report-involved"
        capture_element_box = await get_element_dimensions(page, capture_class)
        if not capture_element_box:
            raise ValueError(f"无法获取元素 '{capture_class}' 的边界框")

        # 设置适当的视口大小
        if element_class == "compact-teams":
            # 对于两队情况，增加额外空间
            extra_height = 320 if count == 2 else 100
            viewport_size = {
                "width": int(main_element_box["width"] + 20 * count),
                "height": min(3240, max(1080, int(capture_element_box["height"] + extra_height))),
            }
        else:
            viewport_size = {"width": 1920, "height": min(3240, int(main_element_box["height"] + 100))}

        await page.set_viewport_size(viewport_size)
        await page.wait_for_timeout(1000)
        await expand_scrollable_containers(page)
        await wait_for_all_images_in_viewport(page)

        # 为两队情况再次调整尺寸并展开容器
        if count == 2:
            # 第一次调整后重新获取尺寸
            capture_element_box = await get_element_dimensions(page, capture_class)
            if not capture_element_box:
                raise ValueError(f"无法获取元素 '{capture_class}' 的边界框")

            # 额外增加高度，限制最大高度为 3000
            viewport_size["height"] = min(3000, int(capture_element_box["height"] + 300))
            await page.set_viewport_size(viewport_size)
            await page.wait_for_timeout(1000)

            # 再次展开容器并等待图片加载
            await expand_scrollable_containers(page)
            await wait_for_all_images_in_viewport(page)

            # 最后一次获取实际尺寸
            capture_element_box = await get_element_dimensions(page, capture_class)
            if not capture_element_box:
                raise ValueError(f"无法获取元素 '{capture_class}' 的边界框")

        # 计算裁剪区域
        if element_class == "compact-teams":
            padding_x = 20 * count
            padding_y = 10 if count > 2 else 11
            clip = {
                "x": capture_element_box["x"] - padding_x / 2,
                "y": capture_element_box["y"] - padding_y,
                "width": main_element_box["width"] + padding_x * 2,
                "height": capture_element_box["height"] + padding_y * 2,
            }
        else:
            clip = {
                "x": capture_element_box["x"],
                "y": capture_element_box["y"] - 10,
                "width": main_element_box["width"],
                "height": main_element_box["height"] + 10,
            }

        # 截图并返回
        screenshot = await page.screenshot(clip=clip)
        return screenshot


async def html2pic(
    url: str | None = None,
    html_content: str | None = None,
    element: str = "body",
    hide_elements: list[str] | None = None,
    viewport_width: int = 1920,
    viewport_height: int = 1080,
    full_page: bool = False,
) -> bytes:
    """
    通用网页元素截图函数

    Args:
        url: 要截图的网页URL
        html_content: HTML内容字符串
        element: 要截图的元素选择器
        hide_elements: 需要隐藏的元素列表
        viewport_width: 视口宽度
        viewport_height: 视口高度
        full_page: 是否需要完整页面滚动截图

    Returns:
        图片二进制数据
    """
    return await capture_element(
        url=url,
        html_content=html_content,
        element=element,
        hide_elements=hide_elements,
        viewport_width=viewport_width,
        viewport_height=viewport_height,
        full_page=full_page,
    )


async def html2pic_kmapp(url: str, viewport_width: int = 1280) -> bytes:
    """
    截取 killmail.app 战斗报告并垂直拼合四个区域：

      1. Overview 比分详情（不含 Kill Feed）
      2. Pilots 联盟飞行员分布（隐藏中间比较列，避免重复）
      3. Composition 舰种构成（Ship Type 视图，双侧展开）
      4. 底部战损进度图（舰队强度 + 累计 ISK 损失）

    Args:
        url: killmail.app 战斗报告 URL
        viewport_width: 视口宽度，默认 1280

    Returns:
        PNG 二进制数据
    """
    TITLE_SEL = (
        "#root > div > main > div > "
        "div.shrink-0.border-b.px-5.py-3.border-white\/5"
    )
    SCORE_SEL = (
        "#root > div > main > div > "
        "div.hidden.min-h-0.w-full.flex-col.items-center.overflow-auto.sm\\:flex "
        "> div > div.flex.items-start.gap-6"
    )
    SCROLL_SEL = (
        "#root > div > main > div > "
        "div.hidden.min-h-0.w-full.flex-col.items-center.overflow-auto.sm\\:flex"
    )

    async with get_new_page(
        viewport={"width": viewport_width, "height": 920},
        device_scale_factor=1,
    ) as page:
        await page.goto(url)
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(1500)

        async def _shoot_full_width(selector: str) -> bytes:
            """截图时统一使用 x=0、宽度=viewport_width，保证各分区宽度一致（居中）。"""
            el = await page.wait_for_selector(selector, timeout=8000)
            box = await el.bounding_box()
            return await page.screenshot(
                clip={
                    "x": 0.0,
                    "y": max(0.0, box["y"]),
                    "width": float(viewport_width),
                    "height": box["height"],
                }
            )

        async def _click_tab(text: str) -> None:
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

        # ── 顶部标题栏（始终可见，先截图备用）────────────────────
        title_png = await _shoot_full_width(TITLE_SEL)

        # ── 0. Overview tab（默认显示，先截图）────────────────────
        overview_png = await _shoot_full_width(SCORE_SEL)

        # ── 最先：隐藏底栏速度控件，截底部固定栏，然后永久隐藏底栏────
        # 隐藏播放倍数控件（gap-1 hidden sm:flex，只在 seek 后可见，预先处理）
        await page.evaluate("""() => {
            const ctrlRow = document.querySelector(
                'div.fixed.bottom-0.w-screen div.mb-3.flex.items-center');
            if (!ctrlRow) return;
            for (const el of ctrlRow.children) {
                if (el.textContent?.includes('1x') && el.textContent?.includes('100x')) {
                    el.style.display = 'none';
                }
            }
        }""")
        bottom_box = await page.evaluate("""() => {
            const el = document.querySelector('div.fixed.bottom-0.w-screen');
            const r = el?.getBoundingClientRect();
            return r ? {y: r.y, h: r.height} : null;
        }""")
        bottom_png: bytes | None = None
        if bottom_box and bottom_box["h"] > 0:
            bottom_png = await page.screenshot(
                clip={
                    "x": 0.0,
                    "y": float(bottom_box["y"]),
                    "width": float(viewport_width),
                    "height": float(bottom_box["h"]),
                }
            )
        # 隐藏底栏：避免 Pilots 等内容被 fixed 层遮挡
        await page.evaluate("""() => {
            const bar = document.querySelector('div.fixed.bottom-0.w-screen');
            if (bar) bar.style.display = 'none';
        }""")

        # ── 1. Pilots tab（隐藏：中间比较列 + 队名标题 + 飞行员/损失汇总行）
        await _click_tab("Pilots")

        # 在隐藏汇总行之前读取双方飞行员总数
        total_pilots: int = await page.evaluate(
            """(sel) => {
                const c = document.querySelector(sel);
                if (!c) return 0;
                const num = t => {
                    const m = (t || '').match(/([\\d,]+)\\s*pilots/i);
                    return m ? parseInt(m[1].replace(/,/g, ''), 10) : 0;
                };
                const left  = c.children[0]?.children[1]?.children[0]?.innerText ?? '';
                const right = c.children[2]?.children[1]?.children[0]?.innerText ?? '';
                return num(left) + num(right);
            }""",
            SCORE_SEL,
        )
        logger.debug(f"html2pic_kmapp: 双方飞行员总数={total_pilots}")

        await page.evaluate("""(sel) => {
            const container = document.querySelector(sel);
            if (!container) return;
            // 中间列 (PILOTS 754 v 532 + ISK EFF)
            if (container.children[1]) container.children[1].style.display = 'none';
            // 左右队名标题（children[0/2].children[0]）
            const hideEl = el => { if (el) el.style.display = 'none'; };
            hideEl(container.children[0]?.children[0]);
            hideEl(container.children[2]?.children[0]);
            // 左侧"754 pilots / 59 ships lost"汇总行（children[0].children[1].children[0]）
            hideEl(container.children[0]?.children[1]?.children[0]);
            // 右侧"532 pilots / 130 ships lost"汇总行
            hideEl(container.children[2]?.children[1]?.children[0]);
        }""", SCORE_SEL)
        pilots_png = await _shoot_full_width(SCORE_SEL)

        # ── 2. Composition tab (Ship Type) ───────────────────────
        await _click_tab("Composition")

        # 双方飞行员总数超过 40 时才切换为 Ship Type 粒度
        if total_pilots > 40:
            await page.evaluate("""() => {
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
                let node;
                while ((node = walker.nextNode())) {
                    if (node.children.length === 0
                        && node.textContent?.trim() === 'Ship type'
                        && getComputedStyle(node).cursor === 'pointer') {
                        node.click();
                    }
                }
            }""")
            await page.wait_for_timeout(600)

        # 隐藏 Composition 的中间列 + 队名
        await page.evaluate("""(sel) => {
            const container = document.querySelector(sel);
            if (!container) return;
            if (container.children[1]) container.children[1].style.display = 'none';
            const hideEl = el => { if (el) el.style.display = 'none'; };
            hideEl(container.children[0]?.children[0]);
            hideEl(container.children[2]?.children[0]);
        }""", SCORE_SEL)

        # 解除滚动容器溢出，获取内容完整高度
        comp_h: int = await page.evaluate(
            """(scrollSel) => {
                const container = document.querySelector(scrollSel);
                if (container) {
                    container.style.overflow = 'visible';
                    container.style.height = 'auto';
                    container.style.maxHeight = 'none';
                }
                const inner = container?.querySelector('div > div.flex.items-start.gap-6');
                if (!inner) return 0;
                const r = inner.getBoundingClientRect();
                return Math.ceil(r.height);
            }""",
            SCROLL_SEL,
        )

        if comp_h > 0:
            await page.set_viewport_size({"width": viewport_width, "height": comp_h + 80})
            # 滚动到底再回顶，触发懒渲染
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(400)
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(300)

        comp_png = await _shoot_full_width(SCORE_SEL)

    # ── 拼合 ──────────────────────────────────────────────────────
    parts: list[Image.Image] = [
        Image.open(BytesIO(title_png)).convert("RGB"),
        Image.open(BytesIO(overview_png)).convert("RGB"),
        Image.open(BytesIO(pilots_png)).convert("RGB"),
        Image.open(BytesIO(comp_png)).convert("RGB"),
    ]
    if bottom_png:
        parts.append(Image.open(BytesIO(bottom_png)).convert("RGB"))

    canvas_w = max(img.width for img in parts)
    canvas_h = sum(img.height for img in parts)
    canvas = Image.new("RGB", (canvas_w, canvas_h), (6, 8, 12))
    y_off = 0
    for img in parts:
        canvas.paste(img, (0, y_off))
        y_off += img.height

    out = BytesIO()
    canvas.save(out, format="PNG")
    return out.getvalue()


async def html2gif(
    url: str,
    element: str = "main",
    viewport_width: int = 1280,
    viewport_height: int = 850,
    fps: int = 8,
    min_output_seconds: float = 8.0,
    max_output_seconds: float = 15.0,
    seek_wait_ms: int = 200,
) -> bytes:
    """
    通过 Seek 时间轴逐帧截图生成 GIF（仅适用于带时间轴的 killmail.app 战斗页面）。

    原理：直接按比例点击时间轴 canvas，定位到每个关键帧，无需等待实时播放。
    速度：约 200~500ms/帧，120 帧约需 50 秒，远优于实时录制（约 170 秒）。

    GIF 时长根据战斗总时长自适应，计算公式：total_seconds / 120，结果夹在
    [min_output_seconds, max_output_seconds] 之间（每 2 分钟战斗对应约 1 秒 GIF）。
    无法读取时长时回退到 max_output_seconds。

    Args:
        url: 页面 URL（需含 canvas.block.h-64.w-full 时间轴）
        element: 截图裁剪元素选择器，默认 main
        viewport_width: 视口宽度
        viewport_height: 视口高度
        fps: GIF 帧率
        min_output_seconds: GIF 最短时长（秒），默认 8
        max_output_seconds: GIF 最长时长（秒），默认 15
        seek_wait_ms: 每次 seek 后等待渲染的毫秒数

    Returns:
        GIF 二进制数据

    Raises:
        RuntimeError: 页面无时间轴或未采集到帧
    """
    if fps <= 0:
        raise ValueError("fps 必须大于 0")
    if min_output_seconds <= 0 or max_output_seconds <= 0:
        raise ValueError("输出时长必须大于 0")
    if min_output_seconds > max_output_seconds:
        raise ValueError("min_output_seconds 不能大于 max_output_seconds")

    frame_duration_ms = max(20, int(1000 / fps))
    # n_frames 在读完时长后确定，先用最大值做占位
    n_frames: int = max(2, int(fps * max_output_seconds))

    async with get_new_page(
        viewport={"width": viewport_width, "height": viewport_height},
        device_scale_factor=1,
    ) as page:
        await page.goto(url)
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(1000)

        # 检查时间轴是否存在
        canvas = page.locator("canvas.block.h-64.w-full")
        if await canvas.count() == 0:
            raise RuntimeError("页面无时间轴 canvas，不支持 GIF 生成")

        canvas_box = await canvas.bounding_box()
        if not canvas_box or canvas_box["width"] < 10:
            raise RuntimeError("时间轴 canvas 尺寸异常")

        # 拖动时间轴到最左侧（重置到 0 点）
        cx = canvas_box["x"]
        cy = canvas_box["y"] + canvas_box["height"] / 2
        cw = canvas_box["width"]
        await page.mouse.move(cx + cw - 5, cy)
        await page.mouse.down()
        await page.mouse.move(cx, cy, steps=25)
        await page.mouse.up()
        await page.wait_for_timeout(200)

        # 隐藏播放倍数控件（seek 后出现，截图前移除）
        await page.evaluate("""() => {
            const ctrlRow = document.querySelector(
                'div.fixed.bottom-0.w-screen div.mb-3.flex.items-center');
            if (!ctrlRow) return;
            for (const el of ctrlRow.children) {
                if (el.textContent?.includes('1x') && el.textContent?.includes('100x')) {
                    el.style.display = 'none';
                }
            }
        }""") 

        # 读取战斗总时长，自适应计算 GIF 输出帧数
        try:
            total_seconds: int = await page.evaluate("""
                () => {
                    const m = (document.body.innerText || '').match(
                        /(\\d{2}):(\\d{2}):(\\d{2})\\s*\\/\\s*(\\d{2}):(\\d{2}):(\\d{2})/
                    );
                    if (!m) return 0;
                    return (+m[4]) * 3600 + (+m[5]) * 60 + (+m[6]);
                }
            """)
        except Exception:
            total_seconds = 0

        if total_seconds > 0:
            # 每 2 分钟战斗 ≈ 1 秒 GIF，夹在 [min, max] 范围内
            adaptive = total_seconds / 120.0
            output_seconds = max(min_output_seconds, min(max_output_seconds, adaptive))
        else:
            output_seconds = max_output_seconds

        n_frames = max(2, int(fps * output_seconds))
        logger.debug(
            f"html2gif: 战斗时长={total_seconds}s，GIF={output_seconds:.1f}s，"
            f"帧数={n_frames}，url={url}"
        )

        # 获取截图区域（element 的 bounding box）
        clip: dict | None = None
        try:
            el = await page.wait_for_selector(element, timeout=3000)
            if el:
                box = await el.bounding_box()
                if box and box["width"] > 0 and box["height"] > 0:
                    clip = {
                        "x": max(0.0, box["x"]),
                        "y": max(0.0, box["y"]),
                        "width": min(box["width"], float(viewport_width)),
                        "height": min(box["height"], float(viewport_height)),
                    }
        except Exception:
            clip = None

        frames: list[Image.Image] = []

        for i in range(n_frames):
            ratio = i / (n_frames - 1)
            # 点击时间轴对应位置进行 seek
            await page.mouse.click(cx + ratio * cw, cy)
            await page.wait_for_timeout(seek_wait_ms)
            png = await page.screenshot(clip=clip) if clip else await page.screenshot()
            img = Image.open(BytesIO(png)).convert("P", palette=Image.ADAPTIVE, colors=256)
            frames.append(img)

        logger.debug(f"html2gif: seek 采集完成，共 {len(frames)} 帧，url={url}")

    if not frames:
        raise RuntimeError("未采集到任何帧")

    gif_bytes = BytesIO()
    frames[0].save(
        gif_bytes,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=frame_duration_ms,
        loop=0,
        optimize=True,
        disposal=2,
    )
    return gif_bytes.getvalue()

