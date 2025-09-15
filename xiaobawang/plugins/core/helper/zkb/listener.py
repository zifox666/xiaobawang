import asyncio
import json
import traceback

from httpx import ReadTimeout
from nonebot import logger

from ...config import HEADERS, plugin_config
from ...utils.common.http_client import get_client
from .killmail import km


class ZkbListener:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.running = False
            self.active = False
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
                    plugin_config, proxy=plugin_config.proxy, additional_headers=HEADERS
                ) as websocket:
                    logger.info("已连接到 zkillboard websocket")
                    await websocket.send(json.dumps({"action": "sub", "channel": "killstream"}))

                    self.reconnect_delay = 5

                    while self.running:
                        try:
                            message = await websocket.recv()
                            data = json.loads(message)

                            task = asyncio.create_task(km.check(data))
                            task.add_done_callback(lambda t: t.exception() if t.exception() else None)
                        except (
                            websockets.exceptions.ConnectionClosed,
                            websockets.exceptions.ConnectionClosedError,
                            websockets.exceptions.ConnectionClosedOK,
                        ) as e:
                            logger.warning(f"Websocket 连接关闭: {e}")
                            break
                        except Exception as e:
                            logger.error(f"处理 killmail 时出错: {e}")
                            continue

            except (websockets.exceptions.WebSocketException, ConnectionRefusedError, ConnectionError) as e:
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
                url = f"{plugin_config.zkb_listener_url}?queueID={plugin_config.user_agent}&ttw=5"
                r = await self._client.get(url)
                if r.status_code == 429:
                    logger.warning("请求过于频繁")
                    await asyncio.sleep(5)
                    continue

                r.raise_for_status()
                data = r.json().get("package", None)
                if data:
                    zkb_data = data.get("killmail")
                    zkb_data["zkb"] = data.get("zkb")
                    asyncio.create_task(km.check(zkb_data)) # noqa RUF006
                else:
                    await asyncio.sleep(5)

            except ReadTimeout:
                logger.warning("请求超时")
                await asyncio.sleep(5)

            except Exception as e:
                logger.error(f"获取 redisQ 连接失败: {e}\n{traceback.format_exc()}")
                await asyncio.sleep(self.reconnect_delay)
                self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)

    async def start(self):
        """启动 Killmail 监听器"""
        if self.active:
            logger.info("Killmail 监听器已经在运行中")
            return False

        logger.info("正在启动 Killmail 监听器...")
        self.running = True
        self.active = True

        if plugin_config.zkb_listener_method == "redisQ":
            await self._start_redis_q()
        else:
            await self._start_wss()
        return True

    async def stop(self):
        """停止 Killmail 监听器"""
        if not self.active:
            logger.info("Killmail 监听器未在运行")
            return False

        self.running = False
        self.active = False
        logger.info("正在停止 Killmail 监听器...")
        return True


zkb_listener = ZkbListener()
