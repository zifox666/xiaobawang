import json
import time
from typing import Optional, Dict
from functools import wraps
from datetime import datetime, timedelta

from fastapi import HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from loguru import logger
import base64

from ..helper.token_manager import TokenManager


async def get_current_user(request: Request) -> Dict:
    """
    FastAPI 依赖: 获取当前用户信息
    
    使用方式:
        @router.get("/example")
        async def example_endpoint(current_user: Dict = Depends(get_current_user)):
            qq = current_user["qq"]
            session_id = current_user["session_id"]
            ...
    """
    auth_header = request.headers.get("Authorization", "")
    
    if not auth_header:
        raise HTTPException(status_code=401, detail="缺少认证 Token")
    
    token_data = await TokenManager().verify_token(auth_header)
    
    if not token_data:
        raise HTTPException(status_code=401, detail="无效或过期的 Token")
    
    return token_data


def token_required(f):
    """装饰器: 要求 Token 认证"""
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        request = kwargs.get("request")
        if not request:
            raise HTTPException(status_code=400, detail="请求错误")
        
        current_user = await get_current_user(request)
        kwargs["current_user"] = current_user
        
        return await f(*args, **kwargs)
    
    return decorated_function


class SubscriptionFilter:
    """
    订阅过滤器 - 根据 token 的 session_id 过滤订阅
    
    确保用户只能看到自己 session 的订阅
    """
    
    @staticmethod
    async def filter_by_session(
        subscriptions: list,
        current_user: Dict
    ) -> list:
        """
        按 session_id 过滤订阅
        
        Args:
            subscriptions: 原始订阅列表
            current_user: 当前用户信息 (包含 session_id)
            
        Returns:
            过滤后的订阅列表
        """
        session_id = current_user.get("session_id")
        
        filtered = [
            sub for sub in subscriptions
            if sub.session_id == session_id
        ]
        
        logger.debug(
            f"订阅过滤: session_id={session_id}, "
            f"原始数={len(subscriptions)}, 过滤后={len(filtered)}"
        )
        
        return filtered
    
    @staticmethod
    def add_session_filter_to_query(session_id: str) -> Dict:
        """
        生成数据库查询过滤条件
        
        使用方式 (在 subscription_v2.py 中):
            filter_dict = SubscriptionFilter.add_session_filter_to_query(session_id)
            # 然后将 filter_dict 应用到 SQLAlchemy 查询
        """
        return {
            "session_id": session_id
        }


# 模拟 Redis 的备份和恢复
def backup_tokens(filepath: str = "/tmp/tokens_backup.json"):
    """备份 Tokens (用于开发/测试)"""
    with open(filepath, "w") as f:
        json.dump(TOKENS_STORE, f)
    logger.info(f"Tokens 已备份到: {filepath}")


def restore_tokens(filepath: str = "/tmp/tokens_backup.json"):
    """恢复 Tokens (用于开发/测试)"""
    try:
        with open(filepath, "r") as f:
            global TOKENS_STORE
            TOKENS_STORE = json.load(f)
        logger.info(f"Tokens 已从以下位置恢复: {filepath}")
    except FileNotFoundError:
        logger.warning(f"备份文件不存在: {filepath}")
