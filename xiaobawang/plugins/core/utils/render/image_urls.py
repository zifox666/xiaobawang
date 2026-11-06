"""把模板里写死的图片地址换成配置的地址，在渲染出的 HTML 上统一处理。"""

import re

# 模板中的默认图床：物品图由它托管，实体图只是 301 到官方服务器（且跳转时丢失 ?size=）
TEMPLATE_IMAGE_URL = "https://images.newdoublex.space"
_TYPES = re.compile(re.escape(TEMPLATE_IMAGE_URL) + r"(?=/types/)")
_ENTITIES = re.compile(re.escape(TEMPLATE_IMAGE_URL) + r"(?=/(?:characters|corporations|alliances)/)")


def rewrite_image_urls(html: str, type_base: str, entity_base: str) -> str:
    """
    替换图片地址
    :param html: 渲染后的 HTML
    :param type_base: 物品图标（/types/...）的地址
    :param entity_base: 角色、军团、联盟图片的地址
    """
    html = _TYPES.sub(lambda _: type_base.rstrip("/"), html)
    return _ENTITIES.sub(lambda _: entity_base.rstrip("/"), html)
