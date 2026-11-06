import asyncio
import re

import httpx
from nonebot import logger
from nonebot.exception import ActionFailed

# 协议端的发送失败统一返回 retcode=1200，临时和永久故障只能靠底层 NTQQ 结果码区分：
# 110 已被移出该群；16 对方不是好友。结果码在末尾，前面会回显消息正文，因此必须锚定结尾。
PERMANENT_NTQQ_RESULT = re.compile(r"\{ result: (?:110|16), errMsg: '[^']*' \}\s*$")

# NTQQ 图片上传失败：消息明确未发出，重试不会造成重复
RICH_MEDIA_FAILURE = "rich media transfer failed"
MEDIA_RETRY_DELAYS = (2, 5)


async def send_with_media_retry(send, delays=MEDIA_RETRY_DELAYS):
    """发送图片消息，图片上传失败时重试；其他错误（可能已发出）直接抛出"""
    for delay in delays:
        try:
            return await send()
        except ActionFailed as error:
            if RICH_MEDIA_FAILURE not in repr(error):
                raise
            logger.warning(f"图片上传失败，{delay} 秒后重试")
            await asyncio.sleep(delay)
    return await send()


def classify_error(error):
    """Only retry when rejection/non-delivery is known. Unknown transport results need review."""
    if isinstance(error, (httpx.ConnectError, httpx.ConnectTimeout)):
        return "retry", 0
    if isinstance(error, ActionFailed):
        code = getattr(error, "code", None) or getattr(error, "status_code", None)
        data = getattr(error, "data", None) or getattr(error, "info", None)
        if isinstance(data, dict):
            code = data.get("error_code", data.get("retcode", code))
            if PERMANENT_NTQQ_RESULT.search(str(data.get("message", ""))):
                return "dead", 0
        description = str(getattr(error, "description", "") or "").lower()
        match = re.search(r"retry after (\d+)", description)
        if match:
            return "retry", max(5, int(match.group(1)))
        if code == 429:
            parameters = data.get("parameters", {}) if isinstance(data, dict) else {}
            return "retry", max(5, int(parameters.get("retry_after", 60)))
        if code in (400, 401, 403, 404) or getattr(error, "retcode", None) in (100, 1400, 1401, 1403, 1404):
            return "dead", 0
        if code in (100, 1400, 1401, 1403, 1404) or description.startswith(("forbidden:", "bad request:")):
            return "dead", 0
        return "retry", 0
    return "uncertain", 0
