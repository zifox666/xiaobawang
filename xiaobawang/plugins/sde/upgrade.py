import asyncio
import bz2
import json
from pathlib import Path

import aiofiles
import httpx
from nonebot import logger
from tqdm import tqdm


async def get_github_release_info(repo: str = "zifox666/eve-sde-converter") -> dict:
    """获取GitHub最新release信息"""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()


async def get_sde_download_url_and_version(repo: str = "zifox666/eve-sde-converter") -> tuple[str, str]:
    """获取SDE下载URL和版本号"""
    release_info = await get_github_release_info(repo)
    version = release_info["tag_name"]
    for asset in release_info["assets"]:
        if asset["name"] == "sde.sqlite.bz2":
            return asset["browser_download_url"], version
    raise ValueError("未找到sde.sqlite.bz2资产")


class SDEDownloader:
    """SDE数据库下载和解压工具类"""

    def __init__(self, target_path: Path):
        self.target_path = target_path
        self.download_path = target_path.with_suffix(".bz2")
        self.temp_download_path = target_path.with_suffix(".download")
        self.temp_extract_path = target_path.with_suffix(".temp")
        self.version_file = target_path.parent / "latest-sde.json"

    async def download_with_progress(self, download_url: str) -> bool:
        """下载文件并显示进度条"""
        async with httpx.AsyncClient(follow_redirects=True) as client:
            head_resp = await client.head(download_url, follow_redirects=True)
            total_size = int(head_resp.headers.get("content-length", 0))

            progress_bar = tqdm(
                total=total_size,
                unit="B",
                unit_scale=True,
                desc=f"下载EVE SDE文件 {download_url.split('/')[-1]}",
                ascii=True,
            )

            async with client.stream("GET", download_url, follow_redirects=True) as response:
                response.raise_for_status()

                async with aiofiles.open(self.temp_download_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):
                        await f.write(chunk)
                        progress_bar.update(len(chunk))

            progress_bar.close()

            if self.temp_download_path.exists():
                if self.download_path.exists():
                    self.download_path.unlink()
                self.temp_download_path.rename(self.download_path)
                return True

            return False

    async def extract_bz2(self) -> bool:
        """解压bz2文件并显示进度条"""
        if not self.download_path.exists():
            logger.error(f"压缩文件不存在: {self.download_path}")
            return False

        file_size = self.download_path.stat().st_size

        progress_bar = tqdm(
            total=file_size, unit="B", unit_scale=True, desc=f"解压 {self.download_path.name}", ascii=True
        )

        def _decompress():
            with open(self.download_path, "rb") as source:
                with open(self.temp_extract_path, "wb") as dest:
                    decompressor = bz2.BZ2Decompressor()
                    for data in iter(lambda: source.read(1024 * 1024), b""):
                        progress_bar.update(len(data))
                        dest.write(decompressor.decompress(data))

        await asyncio.to_thread(_decompress)
        progress_bar.close()
        return True

    def clean_temp_files(self):
        """清理临时文件"""
        if self.download_path.exists():
            self.download_path.unlink()
            logger.info("已删除压缩文件")

        if self.temp_download_path.exists():
            self.temp_download_path.unlink()
            logger.info("已删除临时下载文件")

        if self.temp_extract_path.exists():
            self.temp_extract_path.unlink()
            logger.info("已删除临时解压文件")

    async def save_version(self, version: str):
        """保存版本信息到JSON文件"""
        version_data = {"version": version}
        async with aiofiles.open(self.version_file, "w", encoding="utf-8") as f:
            await f.write(json.dumps(version_data, indent=2))
        logger.info(f"已保存SDE版本信息: {version}")

    async def download_and_extract(self, download_url: str, version: str) -> bool:
        """下载并解压SDE数据库"""
        # 创建目标目录
        self.target_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"开始下载SDE数据库: {download_url}")

        try:
            success = await self.download_with_progress(download_url)
            if not success:
                raise RuntimeError(f"下载SDE数据库失败: {download_url}")

            logger.info("下载完成，开始解压...")
            await self.extract_bz2()

            # 重命名解压后的文件
            if self.temp_extract_path.exists():
                if self.target_path.exists():
                    self.target_path.unlink()
                self.temp_extract_path.rename(self.target_path)
                logger.info(f"SDE数据库解压完成并重命名: {self.target_path}")
            else:
                raise RuntimeError("解压失败，未找到临时解压文件")

            # 保存版本信息
            await self.save_version(version)

            self.clean_temp_files()

            return True
        except Exception as e:
            logger.error(f"下载或解压SDE数据库时出错: {e}")
            self.clean_temp_files()

            if self.target_path.exists() and self.target_path.stat().st_size == 0:
                self.target_path.unlink()

            raise e


async def download_and_extract_sde(target_path: Path, repo: str = "zifox666/eve-sde-converter") -> bool:
    """下载并解压SDE数据库的便捷函数"""
    download_url, version = await get_sde_download_url_and_version(repo)
    downloader = SDEDownloader(target_path)
    return await downloader.download_and_extract(download_url, version)


async def get_current_sde_version(db_path: Path) -> str | None:
    """获取当前SDE数据库版本"""
    version_file = db_path.parent / "latest-sde.json"
    if version_file.exists():
        async with aiofiles.open(version_file, encoding="utf-8") as f:
            data = json.loads(await f.read())
            return data.get("version")
    return None


async def get_latest_sde_version(repo: str = "zifox666/eve-sde-converter") -> str:
    """获取最新SDE数据库版本"""
    release_info = await get_github_release_info(repo)
    return release_info["tag_name"]


async def check_sde_update(db_path: Path, repo: str = "zifox666/eve-sde-converter") -> dict:
    """检查SDE数据库更新信息"""
    current_version = await get_current_sde_version(db_path)
    latest_version = await get_latest_sde_version(repo)
    needs_update = current_version != latest_version if current_version else True
    return {
        "current_version": current_version,
        "latest_version": latest_version,
        "needs_update": needs_update
    }
