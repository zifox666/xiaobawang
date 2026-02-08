import asyncio
import traceback
from typing import Any

from nonebot import logger
from nonebot_plugin_orm import get_session

from ...api.killmail import get_zkb_killmail
from ...helper.subscription_v2 import KillmailSubscriptionManagerV2
from ...utils.render import render_template, templates_path
from ..message_queue import queue_killmail_message
from .processor import KillmailProcessor
from .validator_v2 import KillmailValidatorV2


class KillmailHelper:
    """Killmail 主处理类，协调验证、处理和发送流程"""

    def __init__(self):
        self.session = get_session()
        self.subscription_manager = KillmailSubscriptionManagerV2(self.session)
        self.validator = KillmailValidatorV2(self.subscription_manager)
        self.processor = KillmailProcessor()

    async def get(self, kill_id: int) -> dict:
        """
        获取处理好的km json数据
        
        Args:
            kill_id: killmail ID
            
        Returns:
            处理后的 killmail 数据
        """
        raw_data = await get_zkb_killmail(kill_id)
        return await self.processor.process_killmail_data(raw_data)

    async def check(self, data: dict[str, Any]):
        """
        处理接收到的 killmail 数据并检查是否需要推送

        Args:
            data: zkillboard 推送的 killmail 数据
        """
        killmail_id = data.get("killmail_id")
        try:
            if not killmail_id:
                logger.warning("收到无效的 killmail 数据: 缺少 killmail_id")
                return
            logger.debug(f"[{killmail_id}] https://zkillboard.com/kill/{killmail_id}/")

            # 验证并匹配订阅
            matched_sessions = await self.validator.validate_and_match(data)

            if matched_sessions:
                await self._send_matched_killmail(killmail_id, data, matched_sessions)

        except Exception as e:
            logger.exception(f"[{killmail_id}]处理 Killmail 失败: {e}")

    async def _send_matched_killmail(self, killmail_id, data, matched_sessions):
        """向匹配的会话发送击杀邮件"""
        logger.info(f"[{killmail_id}] 将推送到 {len(matched_sessions)} 个会话")

        # 处理 killmail 数据
        html_data = await self.processor.process_killmail_data(data)

        # 渲染图片
        pic = await render_template(
            template_path=templates_path / "killmail",
            template_name="killmail.html.jinja2",
            data=html_data,
            width=665,
            height=100,
        )

        tasks = []
        for (platform, bot_id, session_id, session_type, total_value), reasons in matched_sessions.items():
            reason = " | ".join(reasons)
            text_info = self.processor.generate_killmail_text(html_data, reason)
            tasks.append(
                self.send_killmail(platform, bot_id, session_id, session_type, pic, text_info, killmail_id, total_value)
            )

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    @classmethod
    async def send_killmail(
        cls,
        platform: str,
        bot_id: str,
        session_id: str,
        session_type: str,
        pic: bytes,
        reason: str,
        kill_id: str,
        total_value: float = 0,
    ):
        """发送击杀邮件到指定会话"""
        try:
            logger.info(f"{session_type}:{session_id}: {reason}")

            await queue_killmail_message(
                platform=platform,
                bot_id=bot_id,
                session_id=session_id,
                session_type=session_type,
                pic=pic,
                reason=reason,
                kill_id=kill_id,
                immediate=True if reason == "高价值击杀" or total_value >= 8_000_000_000 else False,
            )

        except Exception as e:
            logger.error(f"准备发送 killmail 失败: {e}\n{traceback.format_exc()}")


km = KillmailHelper()
