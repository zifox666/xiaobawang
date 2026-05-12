"""
battlereport 工具包。

用法示例::

    from xiaobawang.plugins.core.utils.battlereport import render_br

    # scit 来源
    img, url = await render_br('scit', report_id='2cbc843a')

    # killmail.app 来源
    img, url = await render_br('killmail_app', solar_system_id=30002439, time_str='202605061630')

    # warbeacon auto 来源
    img, url = await render_br('warbeacon_auto', solar_system_id=30002439, middle_time='2026-05-06T17:00:00Z')

    # 直接渲染已有 warbeacon 战报
    img, url = await render_br('warbeacon_hash', uuid='b92c98c9-5c1c-459f-bbe5-3d3cf03699d8')
"""

from .br_render import render_br
from .auto_group import perform_auto_teaming, faction_key
from .sources import (
    UnifiedBR,
    fetch_evetools_hash,
    fetch_killmail_app,
    fetch_killmail_app_hash,
    fetch_scit,
    fetch_warbeacon_auto,
    fetch_warbeacon_hash,
)

__all__ = [
    "render_br",
    "perform_auto_teaming",
    "faction_key",
    "UnifiedBR",
    "fetch_evetools_hash",
    "fetch_killmail_app",
    "fetch_killmail_app_hash",
    "fetch_scit",
    "fetch_warbeacon_auto",
    "fetch_warbeacon_hash",
]
