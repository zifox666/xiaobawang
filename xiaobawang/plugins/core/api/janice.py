from ..config import HEADERS, plugin_config
from ..utils.common.http_client import get_client


class JaniceAppraisal:
    """
    Janice 合同估价 API
    """

    def __init__(self, persist: bool = True):
        self.code: str = ""
        self.totalVolume: int = 0
        self.totalBuyPrice: int = 0
        self.totalSplitPrice: int = 0
        self.totalSellPrice: int = 0
        self.janiceUrl: str = ""
        self.client = get_client()

        self.url: str = (
            f"https://janice.e-351.com/api/rest/v1/appraisal?key={plugin_config.EVE_JANICE_API_KEY}&persist={persist}"
        )
        self.headers = HEADERS
        self.headers["content-type"] = "text/plain"

    async def get(self, contract: str):
        """
        获取合同估价数据
        :param contract: 合同数据
        :return:
        """
        data = await self._request(contract)
        self.code = data.get("code", 0)
        self.totalSplitPrice = data["totalSplitPrice"]
        self.totalBuyPrice = data["totalBuyPrice"]
        self.totalSellPrice = data["totalSellPrice"]
        self.totalVolume = data["totalVolume"]
        self.janiceUrl: str = f"https://janice.e-351.com/a/{self.code}"
        return self

    async def _request(self, contract: str):
        response = await self.client.post(
            self.url,
            headers=self.headers,
            content=contract.encode("utf-8"),
        )
        response.raise_for_status()
        return response.json()


janice_api = JaniceAppraisal()
