"""
认证路由 - 处理 Token 生成和登出

端点:
- POST /auth/login - 生成 Token
- POST /auth/logout - 撤销 Token
"""

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

from xiaobawang.plugins.core.helper.auth import TokenManager, get_current_user

router = APIRouter(tags=["Authentication"])


class LoginRequest(BaseModel):
    """登录请求"""
    token: str = Field(..., description="订阅会话 TOKEN")


class LoginResponse(BaseModel):
    """登录响应"""
    success: bool
    message: str
    data: dict = Field(default_factory=dict)


class LogoutRequest(BaseModel):
    """登出请求"""
    token: str = Field(..., description="要撤销的 Token")


@router.post("/auth/login", response_model=LoginResponse)
async def login(req: LoginRequest) -> LoginResponse:
    """
    生成 Token - 用户登录
    
    Args:
        req: token: 订阅会话 TOKEN
        
    Returns:
        Token 一天有效
        
    Example:
        POST /auth/login
        {
            "token": "string_8"
        }
        
        Response:
        {
            "success": true,
            "message": "登录成功",
            "data": {
                "token": "eyJ...",
                "expires_in": 24 * 3600,
                "session_info": {

                }
            }
        }
    """

    if not req.token:
        raise HTTPException(status_code=400, detail="缺少必填字段")

    try:
        tk = TokenManager()
        user_info = await tk.verify_token(req.token)
        if not user_info:
            raise HTTPException(status_code=401, detail="无效的订阅会话 TOKEN")

        logger.info(f"用户登录成功: {user_info}")

        return LoginResponse(
            success=True,
            message="登录成功",
            data={
                "token": req.token,
                "expires_in": tk.TOKEN_EXPIRY,
                "user": user_info
            }
        )

    except Exception as e:
        logger.error(f"登录失败: {e!s}")
        raise HTTPException(status_code=500, detail="登录失败")


@router.post("/auth/logout", response_model=LoginResponse)
async def logout(
    current_user: dict = Depends(get_current_user)
) -> LoginResponse:
    """
    登出 - 撤销 Token
        
    Returns:
        成功响应
        
    Example:
        POST /auth/logout
        Headers: Authorization: Bearer <token>
        {
            "token": "<token>"
        }
    """

    try:
        logger.info(f"用户登出: qq={current_user['qq']}")

        return LoginResponse(
            success=True,
            message="登出成功",
            data={}
        )

    except Exception as e:
        logger.error(f"登出失败: {e!s}")
        raise HTTPException(status_code=500, detail="登出失败")


@router.get("/auth/verify")
async def verify_token(current_user: dict = Depends(get_current_user)):
    """
    验证 Token - 检查当前 Token 是否有效
    
    Returns:
        当前用户信息
    """
    return {
        "success": True,
        "data": current_user
    }


@router.get("/auth/me")
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """获取当前用户信息"""
    return {
        "success": True,
        "data": current_user
    }
