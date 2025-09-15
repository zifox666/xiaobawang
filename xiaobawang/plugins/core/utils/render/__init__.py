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

from nonebot_plugin_htmlrender import (
    get_new_page,
    md_to_pic,
    template_to_pic,
)

# 定义模板路径
templates_path = SRC_PATH / "templates"


async def md2pic(content: str) -> bytes:
    """将 Markdown 内容转换为图片"""
    return await md_to_pic(md=content)


async def html2pic(html_content: str, width: int = 700, height: int = 400) -> bytes:
    """将 HTML 内容转换为图片"""
    async with get_new_page(viewport={"width": width, "height": height}, device_scale_factor=2) as page:
        await page.set_content(html_content)
        pic = await page.screenshot(full_page=True, path="./html2pic.png")
    return pic


async def capture_element(
    url: str | None = None,
    html_content: str | None = None,
    element: str = "body",
    hide_elements: list[str] | None = None,
    output_file: str = "./html2pic.png",
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
        output_file: 输出文件路径
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
        element_handle = await page.wait_for_selector(element)
        if element_handle is None:
            raise ValueError(f"Element '{element}' not found on the page.")

        bounding_box = await element_handle.bounding_box()
        element_width = bounding_box["width"]
        element_height = bounding_box["height"]

        await page.set_viewport_size({"width": int(element_width), "height": int(element_height)})

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

        screenshot = await page.screenshot(
            clip={"x": bounding_box["x"], "y": bounding_box["y"], "width": element_width, "height": element_height}
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
                "height": max(1080, int(capture_element_box["height"] + extra_height)),
            }
        else:
            viewport_size = {"width": 1920, "height": int(main_element_box["height"] + 100)}

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

            # 额外增加高度
            viewport_size["height"] = int(capture_element_box["height"] + 300)
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

