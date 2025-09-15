from io import BytesIO
from pathlib import Path
from typing import Any

from nonebot import logger, require
from PIL import Image

from ...config import SRC_PATH
from .utils import scroll_and_load_all_content, wait_for_all_images_in_viewport

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
            stitched_image = Image.open(BytesIO(screenshot))

        stitched_image.save(output_file)
        with BytesIO() as output:
            stitched_image.save(output, format="PNG")
            return output.getvalue()


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

        if trim_width > 0:
            img = Image.open(BytesIO(screenshot))
            original_width, original_height = img.size

            with BytesIO() as output:
                return output.getvalue()
        else:
            with BytesIO() as output:
                return output.getvalue()


async def html2pic_war_beacon(
    url: str,
    click_text: str | None = None,
    element_class: str = "compact-teams",
) -> bytes:
    """
    截图指定URL的特定元素，支持懒加载和虚拟滚动
    """
    if not url:
        raise ValueError("必须提供URL")

    async with get_new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1) as page:
        await page.route("**/*", lambda route: route.continue_())

        await page.goto(url)

        await page.evaluate("""
            localStorage.setItem('eve-warbeacon-locale', 'zh');
            localStorage.setItem('hideDragDropTip', 'true');
        """)

        await page.reload()
        await page.wait_for_load_state("networkidle")

        load_status = await scroll_and_load_all_content(page)
        logger.info(f"内容加载状态: {load_status}")

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

        count = await page.evaluate("""
            () => {
                const teamsContainer = document.querySelector('.compact-teams');
                if (!teamsContainer) {
                    return 2;
                }

                const teamCards = teamsContainer.querySelectorAll('.compact-team-card');
                return teamCards.length;
            }
        """)

        element_handle = await page.wait_for_selector(f".{element_class}")
        if element_handle is None:
            raise ValueError(f"未找到元素 '.{element_class}'")

        await element_handle.scroll_into_view_if_needed()

        await wait_for_all_images_in_viewport(page)

        bounding_box = await element_handle.bounding_box()
        if not bounding_box:
            raise ValueError(f"无法获取元素 '.{element_class}' 的边界框")

        element_width = bounding_box["width"]
        element_height = bounding_box["height"]

        if element_class == "compact-teams":
            await page.set_viewport_size(
                {"width": int(element_width + 20 * count), "height": int(element_height + 180)}
            )
        else:
            await page.set_viewport_size({"width": 1920, "height": int(element_height + 100)})

        await page.wait_for_timeout(1000)

        await page.evaluate("""
        () => {
            // 尝试找到可能的虚拟滚动容器
            const scrollContainers = Array.from(document.querySelectorAll('.compact-teams, .battle-report-involved'));
            scrollContainers.forEach(container => {
                // 如果容器有滚动功能，强制显示全部内容
                if (container.scrollHeight > container.clientHeight) {
                    // 临时禁用虚拟滚动，强制渲染所有内容
                    const originalStyle = container.style.cssText;
                    container.style.height = 'auto';
                    container.style.maxHeight = 'none';
                    container.style.overflow = 'visible';

                    // 保留修改，让后续截图包含全部内容
                }
            });
        }
        """)

        await wait_for_all_images_in_viewport(page)

        capture_class = ".battle-report-involved"
        element_handle = await page.wait_for_selector(capture_class)
        if element_handle is None:
            raise ValueError(f"未找到元素 {capture_class}")

        bounding_box = await element_handle.bounding_box()
        if not bounding_box:
            raise ValueError(f"无法获取元素 '{capture_class}' 的边界框")

        if element_class == "compact-teams":
            clip = {
                "x": bounding_box["x"] - (20 * count) / 2,
                "y": bounding_box["y"],
                "width": element_width + (20 * count) * 2,
                "height": element_height + 140,
            }
        else:
            clip = {
                "x": bounding_box["x"],
                "y": bounding_box["y"],
                "width": element_width,
                "height": element_height,
            }

        screenshot = await page.screenshot(
            clip=clip
        )

        return screenshot
