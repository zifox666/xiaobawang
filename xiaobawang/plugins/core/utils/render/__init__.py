from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional, Any

from nonebot import require
from PIL import Image

from ...config import SRC_PATH

require("nonebot_plugin_htmlrender")

from nonebot_plugin_htmlrender import (
    md_to_pic,
    template_to_pic,
    get_new_page,
)

# 定义模板路径
templates_path = SRC_PATH  / 'templates'


async def md2pic(content: str) -> bytes:
    """将 Markdown 内容转换为图片"""
    return await md_to_pic(md=content)


async def html2pic(
        html_content: str,
        width: int = 700,
        height: int = 400
) -> bytes:
    """将 HTML 内容转换为图片"""
    async with get_new_page(viewport={"width": width, "height": height}, device_scale_factor=2) as page:
        await page.set_content(html_content)
        pic = await page.screenshot(full_page=True, path="./html2pic.png")
    return pic


async def capture_element(
        url: Optional[str] = None,
        html_content: Optional[str] = None,
        element: str = "body",
        hide_elements: Optional[List[str]] = None,
        output_file: str = "./html2pic.png",
        viewport_width: int = 1920,
        viewport_height: int = 1080,
        full_page: bool = False
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
            viewport={"width": viewport_width, "height": viewport_height},
            device_scale_factor=1
    ) as page:
        # 加载页面
        if url:
            await page.goto(url)
            await page.wait_for_load_state("networkidle")
        elif html_content:
            await page.set_content(html_content)
        else:
            raise ValueError("必须提供 url 或 html_content 其中之一")

        # 隐藏指定元素
        if hide_elements:
            await page.evaluate("""
                (selectors) => {
                    selectors.forEach(selector => {
                        const elements = document.querySelectorAll(selector);
                        elements.forEach(element => {
                            element.style.display = 'none';
                        });
                    });
                }
            """, hide_elements)

        # 等待并选择元素
        element_handle = await page.wait_for_selector(element)
        if element_handle is None:
            raise ValueError(f"未找到元素 '{element}'")

        # 获取元素位置和尺寸
        bounding_box = await element_handle.bounding_box()
        if not bounding_box:
            raise ValueError(f"无法获取元素 '{element}' 的边界框")

        element_width = bounding_box['width']
        element_height = bounding_box['height']

        if full_page:
            # 多次滚动截图模式
            screenshots = []
            viewport_height = min(viewport_height, 1080)

            for offset in range(0, int(element_height), viewport_height):
                # 滚动到元素的指定部分
                await page.evaluate(f"window.scrollTo(0, {offset})")
                await page.wait_for_timeout(500)  # 确保滚动动作完成

                screenshot = await page.screenshot(
                    clip={
                        "x": bounding_box['x'],
                        "y": bounding_box['y'] - offset if bounding_box['y'] > offset else 0,
                        "width": element_width,
                        "height": min(viewport_height, element_height - offset)
                    }
                )
                screenshots.append(screenshot)

            # 拼接截图
            stitched_image = Image.new('RGB', (int(element_width), int(element_height)))
            current_height = 0
            for screenshot in screenshots:
                img = Image.open(BytesIO(screenshot))
                stitched_image.paste(img, (0, current_height))
                current_height += img.height
        else:
            # 单次截图模式
            # 调整视口大小以适应整个元素
            await page.set_viewport_size({"width": int(viewport_width), "height": int(element_height)})
            await page.wait_for_load_state("networkidle")

            # 截图整个元素
            screenshot = await page.screenshot(
                clip={
                    "x": bounding_box['x'],
                    "y": bounding_box['y'],
                    "width": element_width,
                    "height": element_height
                }
            )
            stitched_image = Image.open(BytesIO(screenshot))

        # 保存图片
        stitched_image.save(output_file)
        with BytesIO() as output:
            stitched_image.save(output, format="PNG")
            return output.getvalue()


async def render_template(
        template_path: Path,
        template_name: str,
        data: Dict[str, Any],
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
