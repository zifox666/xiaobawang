"""
自动完成路由 - Zkillboard 实体查询代理

解决前端 CORS 问题，同时缓存查询结果
"""

from fastapi import APIRouter, HTTPException
import httpx
import json
from loguru import logger

from xiaobawang.plugins.core.utils.common.cache import cache

router = APIRouter(tags=["Autocomplete"])

CACHE_TTL = 3600  # 缓存 1 小时


async def _get_zkillboard_data(query: str):
    """从 Zkillboard 获取自动完成数据"""
    if len(query) < 2:
        return []
    
    query_lower = query.lower()
    cache_key = f"autocomplete:zkb:{query_lower}"
    
    # 检查缓存
    cached_data = await cache.get(cache_key)
    if cached_data is not None:
        logger.debug(f"Zkillboard 缓存命中: query={query}")
        return cached_data
    
    try:
        # 调用 Zkillboard API
        url = f"https://zkillboard.com/autocomplete/{query}/"
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url)
            res.raise_for_status()
            data = res.json()
        
        # 缓存结果
        await cache.set(cache_key, data, expire=CACHE_TTL)
        
        logger.info(f"Zkillboard 查询成功: query={query}, results={len(data)}")
        return data
    
    except Exception as e:
        logger.error(f"Zkillboard 查询失败: {str(e)}")
        return []


@router.get("/{query}")
async def autocomplete(query: str):
    """
    实体自动完成查询
    
    Args:
        query: 搜索关键词 (至少 2 个字符)
        
    Returns:
        搜索结果列表
        
    Example:
        GET /autocomplete/phoenix
        
        Response:
        {
            "success": true,
            "query": "phoenix",
            "count": 10,
            "data": [
                {
                    "id": 19726,
                    "name": "Phoenix",
                    "type": "ship",
                    "image": "https://image.eveonline.com/types/19726/icon?size=32"
                },
                ...
            ]
        }
    """
    
    if not query or len(query.strip()) < 2:
        return {
            "success": True,
            "query": query,
            "count": 0,
            "data": []
        }
    
    query = query.strip()
    
    try:
        results = await _get_zkillboard_data(query)
        
        return {
            "success": True,
            "query": query,
            "count": len(results),
            "data": results
        }
    
    except Exception as e:
        logger.error(f"自动完成查询失败: {str(e)}")
        raise HTTPException(status_code=500, detail="查询失败，请重试")


@router.post("/clear-cache")
async def clear_cache():
    """清除自动完成缓存 (用于调试)"""
    try:
        # 清除所有 autocomplete: 开头的缓存键
        redis = cache.redis
        keys = await redis.keys("xiaobawang:core:autocomplete:*")
        if keys:
            await redis.delete(*keys)
        
        return {
            "success": True,
            "message": f"已清除 {len(keys)} 条缓存"
        }
    except Exception as e:
        logger.error(f"清除缓存失败: {str(e)}")
        raise HTTPException(status_code=500, detail="清除缓存失败")
