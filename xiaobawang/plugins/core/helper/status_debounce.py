"""把逐次轮询结果收敛为稳定的服务器在线状态，避免网络抖动被当成开关服。"""

from datetime import datetime, timezone

# 轮询间隔 30 秒，以下单位均为连续轮询次数
ONLINE_CONFIRM_POLLS = 2  # 1 分钟
OFFLINE_CONFIRM_POLLS = 4  # 2 分钟
# DT 窗口外 ESI 持续 5xx 通常只是 ESI 或网络故障，等足够久才认为是计划外停服
ESI_FAILURE_CONFIRM_POLLS = 60  # 30 分钟

# 每日 DT 在 11:00 UTC 开始；这段时间内 ESI 5xx 可视为停服
DT_WINDOW_UTC = ((10, 55), (11, 30))


def in_dt_window(when: datetime) -> bool:
    start, end = DT_WINDOW_UTC
    return start <= (when.hour, when.minute) < end


class StatusDebouncer:
    def __init__(self):
        self.candidate: bool | None = None
        self.count = 0

    def observe(self, online: bool, *, esi_failure: bool = False, when: datetime | None = None) -> bool | None:
        """
        记录一次轮询结果
        :param online: 本次观察到的状态
        :param esi_failure: 本次离线判断仅来自 ESI 5xx，而非明确的低在线人数
        :param when: 观察时间，默认当前 UTC 时间
        :return: 已确认的状态；连续次数不足时返回 None
        """
        if online != self.candidate:
            self.candidate, self.count = online, 0
        self.count += 1

        if online:
            required = ONLINE_CONFIRM_POLLS
        elif esi_failure and not in_dt_window(when or datetime.now(timezone.utc)):
            required = ESI_FAILURE_CONFIRM_POLLS
        else:
            required = OFFLINE_CONFIRM_POLLS
        return online if self.count >= required else None
