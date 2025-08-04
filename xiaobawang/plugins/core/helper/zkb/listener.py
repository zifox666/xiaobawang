import json
import asyncio
import traceback

from nonebot import logger
from nonebot_plugin_orm import get_session

from ..subscription import KillmailSubscriptionManager
from .killmail import km
from ...config import plugin_config, HEADERS
from ...utils.common.http_client import get_client


class ZkbListener:
    def __init__(self):
        self.running = True
        self.reconnect_delay = 5  # 初始重连延迟（秒）
        self.max_reconnect_delay = 300  # 最大重连延迟（秒）

    async def _start_wss(self):
        """启动 Killmail Websocket 监听器"""
        # 403 error when try to connect via python #321
        # https://github.com/zKillboard/zKillboard/issues/321
        import websockets

        while self.running:
            try:
                logger.info("正在连接到 zkillboard websocket...")
                async with websockets.connect(
                        plugin_config,
                        proxy=plugin_config.proxy,
                        additional_headers=HEADERS
                ) as websocket:
                    logger.info("已连接到 zkillboard websocket")
                    await websocket.send(json.dumps({"action": "sub", "channel": "killstream"}))

                    self.reconnect_delay = 5

                    while self.running:
                        try:
                            message = await websocket.recv()
                            data = json.loads(message)

                            asyncio.create_task(km.check(data))
                        except (websockets.exceptions.ConnectionClosed,
                                websockets.exceptions.ConnectionClosedError,
                                websockets.exceptions.ConnectionClosedOK) as e:
                            logger.warning(f"Websocket 连接关闭: {e}")
                            break
                        except Exception as e:
                            logger.error(f"处理 killmail 时出错: {e}")
                            continue

            except (websockets.exceptions.WebSocketException,
                    ConnectionRefusedError,
                    ConnectionError) as e:
                if not self.running:
                    break

                logger.error(f"Websocket 连接失败: {e}, {self.reconnect_delay}秒后重试\n{traceback.format_exc()}")
                await asyncio.sleep(self.reconnect_delay)

                self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)

            except Exception as e:
                logger.error(f"未知错误: {e}, {self.reconnect_delay}秒后重试")
                await asyncio.sleep(self.reconnect_delay)
                self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)

    async def _start_redis_q(self):
        """redisQ 监听器"""
        self._client = get_client()
        while self.running:
            try:
                url = f"{plugin_config.zkb_listener_url}?queueID={plugin_config.user_agent}&ttw=1"
                r = await self._client.get(url)
                r.raise_for_status()
                data = r.json().get("package", None)
                if data:
                    zkb_data = data.get("killmail")
                    zkb_data['zkb'] = data.get("zkb")
                    asyncio.create_task(km.check(zkb_data))
                    await asyncio.sleep(0.1)
                else:
                    await asyncio.sleep(5)

            except Exception as e:
                if r.status_code == 429:
                    logger.warning("请求过于频繁")
                    await asyncio.sleep(2)
                else:
                    logger.error(f"获取 redisQ 连接失败: {e}\n{traceback.format_exc()}")
                    await asyncio.sleep(self.reconnect_delay)
                    self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)

    async def start(self):
        """启动 Killmail 监听器"""
        logger.info("正在启动 Killmail 监听器...")
        if plugin_config.zkb_listener_method == "redisQ":
            await self._start_redis_q()
        else:
            await self._start_wss()

    async def stop(self):
        """停止 Killmail 监听器"""
        self.running = False
        logger.info("正在停止 Killmail 监听器...")


zkb_listener = ZkbListener()
