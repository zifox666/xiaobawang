from .base import BaseClient


class ZkillboardApi(BaseClient):
    """
    Zkillboard API
    """
    def __init__(self):
        super().__init__()
        self._base_url: str = "https://zkillboard.com/api"

