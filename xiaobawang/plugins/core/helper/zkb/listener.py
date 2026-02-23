import asyncio
import traceback
import time

from httpx import ReadTimeout
from nonebot import logger

from ...api.killmail import get_zkb_killmail
from ...config import plugin_config
from ...utils.common.cache import cache as redis_cache
from ...utils.common.http_client import get_client
from .killmail import km

MAX_CONCURRENT = 20  # 同时处理 km.check 的最大并发数
WORKER_COUNT = 10  # 消费者 worker 数量
KM_DEDUP_EXPIRE = 600  # killmail_id 去重缓存有效期（秒）
KM_DEDUP_PREFIX = "zkb:km_seen:"  # Redis 去重 key 前缀
QUEUE_DEPTH_LOG_INTERVAL = 30  # 队列深度监控日志最短间隔（秒）
QUEUE_DEPTH_WARN_THRESHOLD = 200  # 队列积压超过此值时告警

R2Z2_BASE_URL = "https://r2z2.zkillboard.com/ephemeral"  # R2Z2 API 基础地址
R2Z2_SEQUENCE_KEY = "zkb:r2z2:last_sequence"  # Redis 中持久化 sequence 的 key
R2Z2_POLL_INTERVAL = 0.1  # 成功拉取后的轮询间隔（秒），对应 10次/秒
R2Z2_EMPTY_WAIT = 6  # 收到 404 后等待秒数（官方要求最少 6 秒）
R2Z2_RATE_LIMIT_WAIT = 10  # 收到 429 后等待秒数


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
            self.reconnect_delay = 5  # 初始重连延迟（秒）
            self.max_reconnect_delay = 300  # 最大重连延迟（秒）

            # ── 并发 & 队列控制 ──
            self._semaphore = asyncio.Semaphore(MAX_CONCURRENT)
            self._queue: asyncio.Queue[dict] = asyncio.Queue()  # 无界队列，所有 km 都会被处理
            self._workers: list[asyncio.Task] = []
            self._active_tasks: set[asyncio.Task] = set()
            self._last_depth_log: float = 0
            self._stats_deduped: int = 0
            self._stats_processed: int = 0
            self._stats_enqueued: int = 0

            self._initialized = True

    # ── 去重：利用 Redis 缓存已见过的 killmail_id ──────────

    async def _is_km_seen(self, killmail_id: int | str) -> bool:
        """检查 killmail_id 是否已经处理过（Redis 去重）"""
        try:
            if not redis_cache._initialized:
                return False
            key = f"{KM_DEDUP_PREFIX}{killmail_id}"
            return await redis_cache.exists(key)
        except Exception:
            return False

    async def _mark_km_seen(self, killmail_id: int | str):
        """标记 killmail_id 为已处理"""
        try:
            if not redis_cache._initialized:
                return
            key = f"{KM_DEDUP_PREFIX}{killmail_id}"
            await redis_cache.set(key, 1, expire=KM_DEDUP_EXPIRE)
        except Exception:
            pass

    # ── 入队 ──────────────────────────────────────────────

    async def _enqueue(self, data: dict):
        """
        将 killmail 数据入队，所有 km 都会保留，由 worker 慢慢消费。
        仅做 killmail_id 去重过滤。
        """
        killmail_id = data.get("killmail_id")

        if killmail_id and await self._is_km_seen(killmail_id):
            self._stats_deduped += 1
            logger.debug(f"[{killmail_id}] 已处理过，跳过（去重）")
            return

        await self._queue.put(data)
        self._stats_enqueued += 1

        depth = self._queue.qsize()
        now = time.monotonic()
        if depth >= QUEUE_DEPTH_WARN_THRESHOLD and now - self._last_depth_log > QUEUE_DEPTH_LOG_INTERVAL:
            logger.warning(
                f"KM 队列积压: {depth} 条待处理 | "
                f"已入队: {self._stats_enqueued}, 已处理: {self._stats_processed}, 去重: {self._stats_deduped}"
            )
            self._last_depth_log = now
        elif depth > 0 and depth % 100 == 0:
            logger.info(f"KM 队列深度: {depth}")

    # ── Worker ────────────────────────────────────────────

    async def _worker(self, worker_id: int):
        """消费者 worker，从队列取出 km 数据并在信号量限制下处理"""
        logger.debug(f"KM Worker-{worker_id} 已启动")
        while self.running:
            try:
                try:
                    data = await asyncio.wait_for(self._queue.get(), timeout=2.0)
                except asyncio.TimeoutError:
                    continue

                killmail_id = data.get("killmail_id")

                # 二次去重
                if killmail_id and await self._is_km_seen(killmail_id):
                    self._stats_deduped += 1
                    self._queue.task_done()
                    continue

                async with self._semaphore:
                    try:
                        await km.check(data)
                        self._stats_processed += 1
                        if killmail_id:
                            await self._mark_km_seen(killmail_id)
                    except Exception as e:
                        logger.error(f"[{killmail_id}] Worker-{worker_id} 处理 killmail 失败: {e}")

                self._queue.task_done()

            except asyncio.CancelledError:
                logger.debug(f"KM Worker-{worker_id} 被取消")
                break
            except Exception as e:
                logger.error(f"KM Worker-{worker_id} 未知错误: {e}")

        logger.debug(f"KM Worker-{worker_id} 已退出")

    def _start_workers(self):
        """启动 worker 池"""
        for i in range(WORKER_COUNT):
            task = asyncio.create_task(self._worker(i))
            self._workers.append(task)
        logger.info(f"已启动 {WORKER_COUNT} 个 KM Worker，最大并发={MAX_CONCURRENT}")

    async def _stop_workers(self):
        """优雅停止所有 worker"""
        try:
            await asyncio.wait_for(self._queue.join(), timeout=30)
        except asyncio.TimeoutError:
            remaining = self._queue.qsize()
            logger.warning(f"等待队列排空超时，剩余 {remaining} 条未处理")

        for task in self._workers:
            task.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

        for task in self._active_tasks:
            task.cancel()
        if self._active_tasks:
            await asyncio.gather(*self._active_tasks, return_exceptions=True)
        self._active_tasks.clear()

        logger.info(
            f"KM Workers 已全部停止 | "
            f"已入队: {self._stats_enqueued}, 已处理: {self._stats_processed}, 去重: {self._stats_deduped}"
        )

    # ── R2Z2 序列号持久化 ─────────────────────────────────

    async def _get_saved_sequence(self) -> int | None:
        """从 Redis 获取上次保存的 sequence，用于重启后断点续传"""
        try:
            if not redis_cache._initialized:
                return None
            val = await redis_cache.get(R2Z2_SEQUENCE_KEY)
            return int(val) if val is not None else None
        except Exception:
            return None

    async def _save_sequence(self, sequence: int):
        """将当前 sequence 持久化到 Redis（不设过期，永久保存）"""
        try:
            if not redis_cache._initialized:
                return
            await redis_cache.set(R2Z2_SEQUENCE_KEY, sequence, expire=0)
        except Exception:
            pass

    # ── R2Z2 监听器 ──────────────────────────────────────

    async def _start_r2z2(self):
        """
        R2Z2 Ephemeral API 监听器
        基于递增 sequence_id 轮询 Cloudflare R2 Bucket 获取 killmail
        参考: https://github.com/zKillboard/zKillboard/wiki/API-(R2Z2)
        """
        client = get_client()
        sequence: int | None = None

        # 尝试从 Redis 恢复上次的 sequence（断点续传）
        saved_seq = await self._get_saved_sequence()
        if saved_seq is not None:
            sequence = saved_seq
            logger.info(f"R2Z2: 从 Redis 恢复 sequence = {sequence}")

        while self.running:
            try:
                # 如果没有 sequence，从 sequence.json 获取起始值
                if sequence is None:
                    try:
                        r = await client.get(f"{R2Z2_BASE_URL}/sequence.json", timeout=15)
                        r.raise_for_status()
                        sequence = r.json().get("sequence")
                        if sequence is None:
                            logger.error("R2Z2: sequence.json 返回数据无 sequence 字段")
                            await asyncio.sleep(10)
                            continue
                        logger.info(f"R2Z2: 获取起始 sequence = {sequence}")
                    except Exception as e:
                        logger.error(f"R2Z2: 获取 sequence.json 失败: {e}")
                        await asyncio.sleep(self.reconnect_delay)
                        self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)
                        continue

                # 拉取当前 sequence 的 killmail
                try:
                    r = await client.get(f"{R2Z2_BASE_URL}/{sequence}.json", timeout=15)
                except ReadTimeout:
                    logger.warning(f"R2Z2: 请求 {sequence}.json 超时")
                    await asyncio.sleep(R2Z2_EMPTY_WAIT)
                    continue
                except Exception as e:
                    logger.error(f"R2Z2: 请求 {sequence}.json 网络错误: {e}")
                    await asyncio.sleep(self.reconnect_delay)
                    self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)
                    continue

                if r.status_code == 404:
                    # 没有更多 killmail，等待至少 6 秒
                    await asyncio.sleep(R2Z2_EMPTY_WAIT)
                    continue

                if r.status_code == 429:
                    # 触发限流
                    logger.warning(f"R2Z2: 触发限流 (429)，等待 {R2Z2_RATE_LIMIT_WAIT} 秒")
                    await asyncio.sleep(R2Z2_RATE_LIMIT_WAIT)
                    continue

                if r.status_code == 403:
                    logger.error("R2Z2: 访问被拒绝 (403)，可能因轮询过快被封禁，60 秒后重试")
                    await asyncio.sleep(60)
                    continue

                r.raise_for_status()
                raw = r.json()
                logger.debug(raw)

                # R2Z2 格式转换：将 esi 展开到顶层，保留 zkb
                # R2Z2: { killmail_id, hash, esi: { attackers, killmail_id, ... }, zkb: {...}, ... }
                # 目标: { attackers, killmail_id, killmail_time, solar_system_id, victim, zkb }

                esi_data = raw.get("esi", {})
                data = {**esi_data}
                if "zkb" in raw:
                    data["zkb"] = raw["zkb"]
                # 确保顶层有 killmail_id
                if "killmail_id" not in data and "killmail_id" in raw:
                    data["killmail_id"] = raw["killmail_id"]

                # 入队处理
                await self._enqueue(data)

                if sequence % 10 == 0:
                    await self._save_sequence(sequence)

                # 成功，重置重连延迟
                self.reconnect_delay = 5

                # 递增 sequence 并短暂等待（官方建议 10次/秒）
                sequence += 1
                await asyncio.sleep(R2Z2_POLL_INTERVAL)

            except asyncio.CancelledError:
                # 保存当前 sequence 后退出
                if sequence is not None:
                    await self._save_sequence(sequence)
                raise

            except Exception as e:
                logger.error(f"R2Z2: 未知错误: {e}\n{traceback.format_exc()}")
                sequence = None
                await asyncio.sleep(self.reconnect_delay)
                self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)

        # 正常退出时保存 sequence
        if sequence is not None:
            await self._save_sequence(sequence)
            logger.info(f"R2Z2: 已保存 sequence = {sequence}")

    # ── RedisQ 监听器 ────────────────────────────────────

    async def _start_redis_q(self):
        """redisQ 监听器"""
        client = get_client()
        while self.running:
            try:
                url = f"{plugin_config.zkb_listener_url}?queueID={plugin_config.user_agent}&ttw=5"
                r = await client.get(url)
                # https://github.com/zKillboard/RedisQ?tab=readme-ov-file#limitations
                if r.status_code == 429:
                    logger.warning("请求过于频繁, https://github.com/zKillboard/RedisQ?tab=readme-ov-file#limitations")
                    await asyncio.sleep(5)
                    continue

                r.raise_for_status()
                data = r.json().get("package", None)
                if data:
                    zkb_data = await get_zkb_killmail(data.get("killID", 0))
                    zkb_data["zkb"] = data.get("zkb")
                    await self._enqueue(zkb_data)
                else:
                    await asyncio.sleep(5)

            except ReadTimeout:
                logger.warning("请求超时")
                await asyncio.sleep(5)

            except Exception as e:
                logger.error(f"获取 redisQ 连接失败: {e}\n{traceback.format_exc()}")
                await asyncio.sleep(self.reconnect_delay)
                self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)

    # ── 生命周期 ─────────────────────────────────────────

    async def start(self):
        """启动 Killmail 监听器"""
        if self.active:
            logger.info("Killmail 监听器已经在运行中")
            return False

        method = plugin_config.zkb_listener_method
        logger.info(f"正在启动 Killmail 监听器 (模式: {method})...")
        self.running = True
        self.active = True

        # 重置统计
        self._stats_enqueued = 0
        self._stats_deduped = 0
        self._stats_processed = 0

        # 启动 worker 池
        self._start_workers()

        if method == "redisQ":
            await self._start_redis_q()
        elif method == "r2z2":
            await self._start_r2z2()
        else:
            logger.error(f"未知的监听模式: {method}，支持的模式: r2z2, redisQ")
            self.running = False
            self.active = False
            return False
        return True

    async def stop(self):
        """停止 Killmail 监听器"""
        if not self.active:
            logger.info("Killmail 监听器未在运行")
            return False

        self.running = False
        self.active = False
        logger.info("正在停止 Killmail 监听器...")

        await self._stop_workers()

        logger.info("Killmail 监听器已停止")
        return True


zkb_listener = ZkbListener()
