import asyncio
import hashlib
from io import BytesIO
from pathlib import Path
from typing import Any

from nonebot import logger, require
from PIL import Image

from ...config import SRC_PATH
from ..common.cache import cache as redis_cache
from .killmailapp import html2pic_kmapp
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

# 同时只允许一个 War Beacon 截图任务
_WAR_BEACON_SEMAPHORE = asyncio.Semaphore(1)

# 截图缓存时间（3 小时）
_SCREENSHOT_CACHE_TTL = 3 * 60 * 60


async def _paged_screenshot(
    page,
    bounding_box: dict,
    page_height: int = 1080,
    wait_ms: int = 300,
    hide_elements: list[str] | None = None,
) -> bytes:
    """
    分页截图并垂直拼接，替代设置超大视口的截图方式。

    原理：通过 window.scrollTo 逐段滚动到目标位置后截图，读取实际滚动位置
    来计算正确的 clip Y 偏移（处理浏览器 clamp），最后将各段垂直拼接。

    Args:
        page: Playwright Page 对象
        bounding_box: 目标区域 {'x', 'y', 'width', 'height'}，y 为视口坐标，height 须为完整内容高度
        page_height: 每页截图高度（像素），默认 1080
        wait_ms: 每次滚动后等待渲染的毫秒数
        hide_elements: 需要隐藏的元素选择器列表（每页截图前应用）

    Returns:
        拼接后的 PNG 二进制数据
    """
    el_x = float(bounding_box["x"])
    el_y = float(bounding_box["y"])
    el_w = float(bounding_box["width"])
    el_h = float(bounding_box["height"])

    # bounding_box.y 是视口坐标，doc_y 是文档绝对坐标
    current_scroll_y = await page.evaluate("() => window.scrollY")
    doc_y = el_y + current_scroll_y

    if el_h <= page_height:
        # 单张截图：滚动到目标位置，用实际偏移计算 clipY
        await page.evaluate(f"window.scrollTo(0, {doc_y})")
        await page.wait_for_timeout(wait_ms)
        actual_y = await page.evaluate("() => window.scrollY")
        clip_y = doc_y - actual_y
        return await page.screenshot(
            clip={"x": el_x, "y": clip_y, "width": el_w, "height": el_h}
        )

    imgs: list[Image.Image] = []
    offset = 0.0
    max_pages = 5
    page_count = 0
    while offset < el_h and page_count < max_pages:
        target_scroll = doc_y + offset
        await page.evaluate(f"window.scrollTo(0, {target_scroll})")
        await page.wait_for_timeout(wait_ms)
        # 读取实际滚动位置，浏览器可能 clamp 到 [0, bodyH - vpH]
        actual_y = await page.evaluate("() => window.scrollY")
        clip_y = target_scroll - actual_y
        chunk_h = min(float(page_height), el_h - offset)
        chunk = await page.screenshot(
            clip={"x": el_x, "y": clip_y, "width": el_w, "height": chunk_h},
            type="jpeg",
            quality=92,
        )
        imgs.append(Image.open(BytesIO(chunk)).convert("RGB"))
        offset += page_height
        page_count += 1

    canvas = Image.new("RGB", (int(el_w), sum(img.height for img in imgs)))
    y_off = 0
    for img in imgs:
        canvas.paste(img, (0, y_off))
        y_off += img.height

    buf = BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


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
        # 通过 scrollHeight 获取完整内容高度，不受视口裁剪影响
        element_height = await element_handle.evaluate("el => el.scrollHeight")

        page_h = min(viewport_height, 1080)
        return await _paged_screenshot(
            page,
            {"x": bounding_box["x"], "y": bounding_box["y"], "width": element_width, "height": float(element_height)},
            page_height=page_h,
        )


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
    cache_key: str | None = None
    if url:
        _cache_raw = f"{url}|{element}|{click_selector}|{trim_class}"
        cache_key = f"render:br:{hashlib.md5(_cache_raw.encode()).hexdigest()}"
        cached = await redis_cache.get(cache_key)
        if cached is not None:
            return cached

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

        if click_selector:
            try:
                click_element = await page.wait_for_selector(f'[data-tab-id="{click_selector}"]', timeout=1000)
                if click_element:
                    await click_element.click()
                    await page.wait_for_timeout(1000)
                    await page.wait_for_load_state("networkidle")
            except Exception as e:
                logger.error(f"点击元素 '{click_selector}' 失败: {e!s}")

        # 点击后获取完整内容高度（不受视口限制）
        element_height = await element_handle.evaluate("el => el.scrollHeight")

        clip_width = element_width
        clip_x = bounding_box["x"]
        if trim_width and trim_width * 2 < element_width:
            clip_width = element_width - trim_width * 2
            clip_x = bounding_box["x"] + trim_width

        screenshot = await _paged_screenshot(
            page,
            {"x": clip_x, "y": bounding_box["y"], "width": clip_width, "height": float(element_height)},
        )

    if cache_key:
        await redis_cache.set(cache_key, screenshot, _SCREENSHOT_CACHE_TTL)
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

    cache_key = f"render:war_beacon:{hashlib.md5(f'{url}|{click_text}|{element_class}'.encode()).hexdigest()}"
    cached = await redis_cache.get(cache_key)
    if cached is not None:
        return cached

    async with _WAR_BEACON_SEMAPHORE:
        # 获得信号量后再次检查缓存（防止重复渲染）
        cached = await redis_cache.get(cache_key)
        if cached is not None:
            return cached

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
                extra_height = 320 if count == 2 else 100
                viewport_size = {
                    "width": int(main_element_box["width"] + 20 * count),
                    "height": min(3800, max(1080, int(capture_element_box["height"] + extra_height))),
                }
            else:
                viewport_size = {"width": 1920, "height": min(3800, int(main_element_box["height"] + 100))}

            await page.set_viewport_size(viewport_size)
            await page.wait_for_timeout(1000)
            await expand_scrollable_containers(page)
            await wait_for_all_images_in_viewport(page)

            # 为两队情况再次调整尺寸并展开容器
            if count == 2:
                capture_element_box = await get_element_dimensions(page, capture_class)
                if not capture_element_box:
                    raise ValueError(f"无法获取元素 '{capture_class}' 的边界框")

                # 限制最大高度为 3800
                viewport_size["height"] = min(3800, int(capture_element_box["height"] + 300))
                await page.set_viewport_size(viewport_size)
                await page.wait_for_timeout(1000)

                # 再次展开可滚动容器
                await expand_scrollable_containers(page)
                await wait_for_all_images_in_viewport(page)

                # 再次获取捕获元素尺寸
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

            screenshot = await page.screenshot(clip=clip)

        await redis_cache.set(cache_key, screenshot, _SCREENSHOT_CACHE_TTL)
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


# html2pic_kmapp moved to killmailapp.py — imported above


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

