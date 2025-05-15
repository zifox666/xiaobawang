import os
import signal
import subprocess
from pathlib import Path
from typing import Tuple, Optional, Callable
from nonebot import logger

import httpx


class GitHubAutoUpdater:
    """
    用于检测 GitHub 仓库更新并自动升级重启的工具类
    """
    def __init__(
         self,
         repo_owner: str,
         repo_name: str,
         local_repo_path: str = None,
         restart_command: str = None,
         pre_update_hook: Callable = None,
         post_update_hook: Callable = None
    ):
        """
        初始化自动更新器

        Args:
            repo_owner: GitHub 仓库所有者
            repo_name: GitHub 仓库名称
            local_repo_path: 本地仓库路径，默认为当前目录
            restart_command: 重启命令，默认为 None (使用 sys.executable 重启)
            pre_update_hook: 更新前执行的钩子函数
            post_update_hook: 更新后执行的钩子函数
        """
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.local_repo_path = Path(local_repo_path or os.getcwd())
        self.restart_command = restart_command
        self.pre_update_hook = pre_update_hook
        self.post_update_hook = post_update_hook
        self.api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/commits"

    async def get_remote_latest_commit(self, branch: str = "main") -> Optional[str]:
        """
        获取远程仓库最新的 commit hash

        Args:
            branch: 分支名称，默认为 main

        Returns:
            最新的 commit hash，如果发生错误则返回 None
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_url}?sha={branch}&per_page=1",
                    headers={"Accept": "application/vnd.github.v3+json"}
                )
                response.raise_for_status()
                commits = response.json()
                if commits and isinstance(commits, list) and len(commits) > 0:
                    return commits[0]["sha"]
                return None
        except Exception as e:
            logger.error(f"获取远程提交失败: {e}")
            return None

    def get_local_commit(self) -> Optional[str]:
        """
        获取本地当前的 commit hash

        Returns:
            当前的 commit hash，如果发生错误则返回 None
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.local_repo_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except Exception as e:
            logger.error(f"获取本地提交失败: {e}")
            return None

    async def needs_upgrade(self, branch: str = "main") -> Tuple[bool, Optional[str], Optional[str]]:
        """
        判断是否需要升级

        Args:
            branch: 分支名称，默认为 main

        Returns:
            (是否需要升级, 本地commit hash, 远程最新commit hash)的元组
        """
        local_commit = self.get_local_commit()
        remote_commit = await self.get_remote_latest_commit(branch)

        if local_commit is None or remote_commit is None:
            return False, local_commit, remote_commit

        return local_commit != remote_commit, local_commit, remote_commit

    def update(self, branch: str = "main") -> bool:
        """
        更新本地仓库

        Args:
            branch: 要更新的分支名称

        Returns:
            更新是否成功
        """
        try:
            if self.pre_update_hook:
                self.pre_update_hook()

            result = subprocess.run(
                ["git", "pull", "origin", branch],
                cwd=self.local_repo_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            if result.returncode != 0:
                logger.error(f"仓库更新失败: {result.stderr}")
                return False

            logger.info(f"仓库更新成功: {result.stdout}")

            if self.post_update_hook:
                self.post_update_hook()

            return True
        except Exception as e:
            logger.error(f"更新仓库时出错: {e}")
            return False

    async def check(self, branch: str = "main") -> bool:
        """
        检查、更新并可选地重启应用

        Args:
            branch: 分支名称，默认为 main

        Returns:
            是否进行了更新
        """
        needs_upgrade, local_hash, remote_hash = await self.needs_upgrade(branch)

        if not needs_upgrade:
            logger.info(f"当前已是最新版本: {local_hash[:7]}")
            return False

        logger.info(f"发现新版本! 当前版本: {local_hash[:7]}, 最新版本: {remote_hash[:7]}")

        update_success = self.update(branch)
        if not update_success:
            logger.error("更新失败，请手动更新")
            os.kill(os.getpid(), signal.SIGINT)
            return False
        else:
            logger.info("更新成功，请重启应用")
            os.kill(os.getpid(), signal.SIGINT)
            return True
