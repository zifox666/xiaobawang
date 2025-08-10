import asyncio
import bz2
from pathlib import Path

import aiofiles
import httpx
from nonebot import logger
from tqdm import tqdm


class SDEDownloader:
    """SDE数据库下载和解压工具类"""

    def __init__(self, download_url: str, target_path: Path):
        self.download_url = download_url
        self.target_path = target_path
        self.download_path = target_path.with_suffix(".bz2")
        self.temp_download_path = target_path.with_suffix(".download")

    async def download_with_progress(self) -> bool:
        """下载文件并显示进度条"""
        async with httpx.AsyncClient() as client:
            head_resp = await client.head(self.download_url)
            total_size = int(head_resp.headers.get("content-length", 0))

            progress_bar = tqdm(
                total=total_size,
                unit="B",
                unit_scale=True,
                desc=f"下载EVE SDE文件 {self.download_url.split('/')[-1]}",
                ascii=True,
            )

            async with client.stream("GET", self.download_url) as response:
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
                with open(self.target_path, "wb") as dest:
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

    async def download_and_extract(self) -> bool:
        """下载并解压SDE数据库"""
        # 创建目标目录
        self.target_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"开始下载SDE数据库: {self.download_url}")

        try:
            success = await self.download_with_progress()
            if not success:
                raise RuntimeError(f"下载SDE数据库失败: {self.download_url}")

            logger.info("下载完成，开始解压...")
            await self.extract_bz2()
            logger.info(f"SDE数据库解压完成: {self.target_path}")

            self.clean_temp_files()

            return True
        except Exception as e:
            logger.error(f"下载或解压SDE数据库时出错: {e}")
            self.clean_temp_files()

            if self.target_path.exists() and self.target_path.stat().st_size == 0:
                self.target_path.unlink()

            raise e


async def download_and_extract_sde(download_url: str, target_path: Path) -> bool:
    """下载并解压SDE数据库的便捷函数"""
    downloader = SDEDownloader(download_url, target_path)
    return await downloader.download_and_extract()
