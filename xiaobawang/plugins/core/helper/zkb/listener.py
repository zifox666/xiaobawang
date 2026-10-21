"""Collectors persist each event before advancing the source cursor."""
import asyncio

from nonebot import logger

from ...api.killmail import get_zkb_killmail
from ...config import plugin_config
from ...utils.common.http_client import get_client
from ..push.service import push_service

R2Z2_BASE_URL = "https://r2z2.zkillboard.com/ephemeral"
# A single source event is retried this many times before it is skipped loudly,
# so one poison payload can never stall the whole pipeline.
MAX_SOURCE_ATTEMPTS = 10


class ZkbListener:
    def __init__(self):
        self.running = False
        self.active = False
        self.task = None

    async def _enqueue(self, data, sequence=None):
        kill_id = data.get("killmail_id")
        if not kill_id:
            raise ValueError("Source event has no killmail_id")
        await push_service.store.ingest(
            f"killmail:{kill_id}", "killmail", data,
            cursor=("r2z2", {"sequence": sequence + 1}) if sequence is not None else None,
        )

    async def _start_r2z2(self):
        saved = await push_service.store.cursor("r2z2")
        sequence = saved.get("sequence") if saved else None
        delay = 5
        failures = 0
        client = get_client()
        while self.running:
            try:
                if sequence is None:
                    response = await client.get(f"{R2Z2_BASE_URL}/sequence.json", timeout=15)
                    response.raise_for_status()
                    sequence = int(response.json()["sequence"])
                response = await client.get(f"{R2Z2_BASE_URL}/{sequence}.json", timeout=15)
                if response.status_code in (404, 429, 403):
                    await asyncio.sleep({404: 6, 429: 10, 403: 60}[response.status_code])
                    continue
                response.raise_for_status()
                raw = response.json()
                data = dict(raw.get("esi", {}))
                data["killmail_id"] = data.get("killmail_id") or raw.get("killmail_id")
                data["zkb"] = raw.get("zkb", {})
                await self._enqueue(data, sequence)
                sequence += 1
                failures, delay = 0, 5
                await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                raise
            except ValueError as error:
                # Deterministic data problem before any persistence: skip the sequence.
                logger.error(f"R2Z2 sequence={sequence} 事件无法入库，跳过: {error}")
                if await self._skip_sequence(sequence):
                    sequence += 1
                    failures, delay = 0, 5
                else:
                    # The database is unavailable; back off and retry the same sequence.
                    failures += 1
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 300)
            except Exception:
                failures += 1
                if failures >= MAX_SOURCE_ATTEMPTS:
                    logger.critical(
                        f"R2Z2 sequence={sequence} 连续 {failures} 次接收失败，跳过该事件以恢复管道"
                    )
                    if await self._skip_sequence(sequence):
                        sequence += 1
                        failures, delay = 0, 5
                        continue
                    # The database is down too; keep retrying the same sequence.
                    failures = MAX_SOURCE_ATTEMPTS - 1
                # Keep the same sequence on DB/parse/network failure. Never jump to the live head.
                logger.exception(f"R2Z2 sequence={sequence} 接收失败（第 {failures} 次），将重试同一事件")
                await asyncio.sleep(delay)
                delay = min(delay * 2, 300)

    async def _skip_sequence(self, sequence):
        """Advance the persisted cursor past an unprocessable event; False when the DB is unavailable."""
        try:
            await push_service.store.skip_cursor("r2z2", {"sequence": sequence + 1})
            return True
        except Exception:
            logger.exception(f"R2Z2 sequence={sequence} 跳过游标推进失败，将重试同一事件")
            return False

    async def _start_redis_q(self):
        client = get_client()
        package = None
        failures = 0
        while self.running:
            try:
                if package is None:
                    response = await client.get(
                        plugin_config.zkb_listener_url,
                        params={"queueID": plugin_config.user_agent, "ttw": 5},
                    )
                    response.raise_for_status()
                    package = response.json().get("package")
                if package:
                    data = await get_zkb_killmail(package["killID"])
                    data["zkb"] = package.get("zkb", {})
                    await self._enqueue(data)
                    package, failures = None, 0
                else:
                    await asyncio.sleep(5)
            except asyncio.CancelledError:
                raise
            except Exception:
                failures += 1
                if package is not None and failures >= MAX_SOURCE_ATTEMPTS:
                    logger.critical(
                        f"RedisQ killID={package.get('killID')} 连续 {failures} 次处理失败，丢弃该事件以恢复管道"
                    )
                    package, failures = None, 0
                else:
                    logger.exception("RedisQ 接收失败，保留当前事件重试")
                await asyncio.sleep(5)

    async def start(self):
        if self.active:
            return False
        self.running = self.active = True
        self.task = asyncio.current_task()
        try:
            if plugin_config.zkb_listener_method == "r2z2":
                await self._start_r2z2()
            elif plugin_config.zkb_listener_method == "redisQ":
                await self._start_redis_q()
            else:
                raise ValueError("zkb_listener_method must be r2z2 or redisQ")
        finally:
            self.running = self.active = False
            self.task = None
        return True

    async def stop(self):
        self.running = False
        if self.task and self.task is not asyncio.current_task():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        return True


zkb_listener = ZkbListener()
