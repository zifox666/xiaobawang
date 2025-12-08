import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from nonebot_plugin_orm import AsyncSession, get_session
from pydantic import BaseModel, Field, field_validator
from loguru import logger

from ..db.models.killmail import KillmailSubscription
from ..helper.subscription_v2 import KillmailSubscriptionManagerV2
from ..helper.auth import get_current_user
from ..helper.zkb.score_rules import ScoreRules
from sqlalchemy import select, func

router = APIRouter()


# ============================================================================
# 数据模型
# ============================================================================


class SubscriptionConditionConfig(BaseModel):
    """订阅条件配置"""
    logic: str = Field(default="AND", description="AND/OR")
    conditions: list[dict[str, Any]] = Field(default_factory=list, description="条件列表")
    groups: list[dict[str, Any]] = Field(default_factory=list, description="条件组列表")


class SubscriptionCreate(BaseModel):
    """创建订阅"""
    name: str = Field(description="订阅名称")
    description: str | None = Field(default=None, description="订阅描述")
    platform: str = Field(description="平台")
    bot_id: str = Field(description="机器人ID")
    session_id: str = Field(description="会话ID")
    session_type: str = Field(description="会话类型")
    min_value: float = Field(default=100_000_000, description="最低价值")
    max_age_days: int | None = Field(default=None, description="最大天数")
    condition_groups: dict[str, Any] | str = Field(description="条件组配置")
    
    @field_validator('condition_groups', mode='before')
    @classmethod
    def parse_condition_groups(cls, v):
        """自动解析 JSON 字符串为字典"""
        if isinstance(v, str):
            return json.loads(v)
        return v


class SubscriptionUpdate(BaseModel):
    """更新订阅"""
    name: str | None = Field(default=None, description="订阅名称")
    description: str | None = Field(default=None, description="订阅描述")
    min_value: float | None = Field(default=None, description="最低价值")
    max_age_days: int | None = Field(default=None, description="最大天数")
    is_enabled: bool | None = Field(default=None, description="是否启用")
    condition_groups: dict[str, Any] | str | None = Field(default=None, description="条件组配置")
    
    @field_validator('condition_groups', mode='before')
    @classmethod
    def parse_condition_groups(cls, v):
        """自动解析 JSON 字符串为字典"""
        if v is None:
            return None
        if isinstance(v, str):
            return json.loads(v)
        return v


class SubscriptionResponse(BaseModel):
    """订阅响应"""
    id: int
    name: str
    description: str | None
    platform: str
    bot_id: str
    session_id: str
    session_type: str
    min_value: float
    max_age_days: int | None
    is_enabled: bool
    condition_groups: dict[str, Any]
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class SubscriptionListResponse(BaseModel):
    """订阅列表响应"""
    total: int
    page: int
    page_size: int
    data: list[SubscriptionResponse]


class SubscriptionTemplate(BaseModel):
    """订阅模板"""
    name: str
    description: str
    config: dict[str, Any]


class APIResponse(BaseModel):
    """API响应"""
    success: bool
    message: str = ""
    data: Any = None


# ============================================================================
# 辅助函数
# ============================================================================


def get_manager(session: AsyncSession) -> KillmailSubscriptionManagerV2:
    """获取订阅管理器"""
    return KillmailSubscriptionManagerV2(session)


# ============================================================================
# API 路由
# ============================================================================


@router.get("/templates", summary="获取所有模板列表")
async def list_templates() -> dict[str, SubscriptionTemplate]:
    """获取所有可用的订阅模板"""
    try:
        template_names = [
            "high_value",
            "alliance_loss",
            "wormhole_label",
            "capital_loss",
            "f1_heavy",
            "nullsec_fight",
            "supercap_vs_goons",
            "faction_war",
        ]

        from ..helper.subscription_v2 import KillmailSubscriptionManagerV2
        manager = KillmailSubscriptionManagerV2(None)

        templates = {}
        for name in template_names:
            template = manager.get_subscription_template(name)
            if template:
                templates[name] = SubscriptionTemplate(
                    name=template["name"],
                    description=template["description"],
                    config=template["config"],
                )

        return templates

    except Exception as e:
        logger.error(f"获取模板列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取模板列表失败: {str(e)}")


@router.get("", summary="获取订阅列表")
async def list_subscriptions(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    platform: str | None = Query(None, description="平台过滤"),
    bot_id: str | None = Query(None, description="机器人ID过滤"),
    session_id: str | None = Query(None, description="会话ID过滤"),
    is_enabled: bool | None = Query(None, description="启用状态过滤"),
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> SubscriptionListResponse:
    """
    获取订阅列表 - 只返回当前用户的订阅

    支持分页和多条件过滤
    
    note: 默认过滤 session_id，确保用户只能看到自己的订阅
    """
    try:
        # 构建查询条件
        query = select(KillmailSubscription)

        # ===== 重要: 按 session_id 过滤，确保数据隔离 =====
        query = query.where(KillmailSubscription.session_id == current_user["session_id"])

        # 应用其他过滤条件
        if platform:
            query = query.where(KillmailSubscription.platform == platform)
        if bot_id:
            query = query.where(KillmailSubscription.bot_id == bot_id)
        if session_id and session_id == current_user["session_id"]:
            # 允许用户显式指定自己的 session_id，但不能跨 session
            query = query.where(KillmailSubscription.session_id == session_id)
        if is_enabled is not None:
            query = query.where(KillmailSubscription.is_enabled == is_enabled)

        # 获取总数（同样强制当前用户 session_id）
        count_query = select(func.count(KillmailSubscription.id)).select_from(KillmailSubscription)
        count_query = count_query.where(KillmailSubscription.session_id == current_user["session_id"])
        if platform:
            count_query = count_query.where(KillmailSubscription.platform == platform)
        if bot_id:
            count_query = count_query.where(KillmailSubscription.bot_id == bot_id)
        if session_id and session_id == current_user["session_id"]:
            count_query = count_query.where(KillmailSubscription.session_id == session_id)
        if is_enabled is not None:
            count_query = count_query.where(KillmailSubscription.is_enabled == is_enabled)

        total_result = await session.execute(count_query)
        total = total_result.scalar() or 0

        # 分页
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        # 执行查询
        result = await session.execute(query)
        subscriptions = result.scalars().all()

        # 转换响应
        data = []
        for sub in subscriptions:
            try:
                condition_groups = json.loads(sub.condition_groups)
            except json.JSONDecodeError:
                condition_groups = {}

            data.append(
                SubscriptionResponse(
                    id=sub.id,
                    name=sub.name,
                    description=sub.description,
                    platform=sub.platform,
                    bot_id=sub.bot_id,
                    session_id=sub.session_id,
                    session_type=sub.session_type,
                    min_value=sub.min_value,
                    max_age_days=sub.max_age_days,
                    is_enabled=sub.is_enabled,
                    condition_groups=condition_groups,
                    created_at=sub.created_at.isoformat(),
                    updated_at=sub.updated_at.isoformat(),
                )
            )

        return SubscriptionListResponse(
            total=total,
            page=page,
            page_size=page_size,
            data=data,
        )

    except Exception as e:
        logger.error(f"获取订阅列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取订阅列表失败: {str(e)}")


@router.get("/score-rules", summary="获取积分规则配置")
async def get_score_rules() -> dict[str, Any]:
    """
    获取订阅条件积分规则配置
    
    返回所有实体类型和标签的积分倍率,供前端展示（无需认证）
    """
    try:
        return {
            "entity_scores": ScoreRules.ENTITY_SCORE,
            "label_scores": ScoreRules.LABEL_SCORE,
            "entity_types": ScoreRules.get_all_entity_types(),
            "labels": ScoreRules.get_all_labels(),
        }
    except Exception as e:
        logger.error(f"获取积分规则失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取积分规则失败: {str(e)}")


@router.get("/{sub_id}", summary="获取订阅详情")
async def get_subscription(
    sub_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> SubscriptionResponse:
    """获取单个订阅的详情 - 仅限当前用户的订阅"""
    try:
        # 同时检查 ID 和 session_id，确保用户只能访问自己的订阅
        query = select(KillmailSubscription).where(
            KillmailSubscription.id == sub_id,
            KillmailSubscription.session_id == current_user["session_id"]
        )
        result = await session.execute(query)
        sub = result.scalar_one_or_none()

        if not sub:
            raise HTTPException(status_code=404, detail=f"订阅 {sub_id} 不存在")

        try:
            condition_groups = json.loads(sub.condition_groups)
        except json.JSONDecodeError:
            condition_groups = {}

        return SubscriptionResponse(
            id=sub.id,
            name=sub.name,
            description=sub.description,
            platform=sub.platform,
            bot_id=sub.bot_id,
            session_id=sub.session_id,
            session_type=sub.session_type,
            min_value=sub.min_value,
            max_age_days=sub.max_age_days,
            is_enabled=sub.is_enabled,
            condition_groups=condition_groups,
            created_at=sub.created_at.isoformat(),
            updated_at=sub.updated_at.isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取订阅失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取订阅失败: {str(e)}")


@router.post("", summary="创建订阅")
async def create_subscription(
    data: SubscriptionCreate,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> APIResponse:
    """创建新的订阅 - 自动关联到当前用户的 session_id"""
    try:
        manager = get_manager(session)

        # 创建订阅
        sub_id = await manager.create_subscription(
            platform=data.platform,
            bot_id=data.bot_id,
            session_id=current_user["session_id"],  # 强制使用用户的 session_id
            session_type=current_user["session_type"],  # 强制使用用户的 session_type
            name=data.name,
            description=data.description,
            min_value=data.min_value,
            max_age_days=data.max_age_days,
            condition_config=data.condition_groups,
        )

        if not sub_id:
            raise HTTPException(status_code=400, detail="创建订阅失败")

        return APIResponse(
            success=True,
            message="订阅创建成功",
            data={"sub_id": sub_id},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建订阅失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建订阅失败: {str(e)}")


@router.put("/{sub_id}", summary="更新订阅")
async def update_subscription(
    sub_id: int,
    data: SubscriptionUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> APIResponse:
    """更新订阅 - 仅限当前用户的订阅"""
    try:
        manager = get_manager(session)

        # 检查订阅是否存在，并确保属于当前用户
        query = select(KillmailSubscription).where(
            KillmailSubscription.id == sub_id,
            KillmailSubscription.session_id == current_user["session_id"]
        )
        result = await session.execute(query)
        sub = result.scalar_one_or_none()

        if not sub:
            raise HTTPException(status_code=404, detail=f"订阅 {sub_id} 不存在")

        # 构建更新数据
        update_data = {}
        if data.name is not None:
            update_data["name"] = data.name
        if data.description is not None:
            update_data["description"] = data.description
        if data.min_value is not None:
            update_data["min_value"] = data.min_value
        if data.max_age_days is not None:
            update_data["max_age_days"] = data.max_age_days
        if data.is_enabled is not None:
            update_data["is_enabled"] = data.is_enabled
        if data.condition_groups is not None:
            update_data["condition_groups"] = data.condition_groups

        if not update_data:
            return APIResponse(
                success=True,
                message="没有需要更新的数据",
                data=None,
            )

        # 执行更新
        success = await manager.update_subscription(sub_id, **update_data)

        if not success:
            raise HTTPException(status_code=400, detail="更新订阅失败")

        return APIResponse(
            success=True,
            message="订阅更新成功",
            data=None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新订阅失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新订阅失败: {str(e)}")


@router.delete("/{sub_id}", summary="删除订阅")
async def delete_subscription(
    sub_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> APIResponse:
    """删除订阅 - 仅限当前用户的订阅"""
    try:
        manager = get_manager(session)

        # 检查订阅是否存在，并确保属于当前用户
        query = select(KillmailSubscription).where(
            KillmailSubscription.id == sub_id,
            KillmailSubscription.session_id == current_user["session_id"]
        )
        result = await session.execute(query)
        sub = result.scalar_one_or_none()

        if not sub:
            raise HTTPException(status_code=404, detail=f"订阅 {sub_id} 不存在")

        # 执行删除
        success = await manager.delete_subscription(sub_id)

        if not success:
            raise HTTPException(status_code=400, detail="删除订阅失败")

        return APIResponse(
            success=True,
            message="订阅删除成功",
            data=None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除订阅失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除订阅失败: {str(e)}")


@router.get("/templates/{template_name}", summary="获取订阅模板")
async def get_template(template_name: str) -> SubscriptionTemplate:
    """获取预定义的订阅模板"""
    try:
        # 创建临时管理器获取模板
        # 这里不需要真实的session,因为只是读取内存数据
        from ..helper.subscription_v2 import KillmailSubscriptionManagerV2
        manager = KillmailSubscriptionManagerV2(None)

        template = manager.get_subscription_template(template_name)

        if not template:
            raise HTTPException(status_code=404, detail=f"模板 {template_name} 不存在")

        return SubscriptionTemplate(
            name=template["name"],
            description=template["description"],
            config=template["config"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取模板失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取模板失败: {str(e)}")


@router.get("/stats/summary", summary="获取订阅统计")
async def get_subscription_stats(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """获取订阅统计信息"""
    try:
        # 总数
        total_result = await session.execute(select(func.count(KillmailSubscription.id)))
        total = total_result.scalar() or 0

        # 启用数
        enabled_result = await session.execute(
            select(func.count(KillmailSubscription.id)).where(KillmailSubscription.is_enabled == True)
        )
        enabled = enabled_result.scalar() or 0

        # 禁用数
        disabled = total - enabled

        # 按平台统计
        platform_result = await session.execute(
            select(KillmailSubscription.platform, func.count(KillmailSubscription.id)).group_by(
                KillmailSubscription.platform
            )
        )
        platform_stats = dict(platform_result.all())

        # 按会话类型统计
        session_type_result = await session.execute(
            select(KillmailSubscription.session_type, func.count(KillmailSubscription.id)).group_by(
                KillmailSubscription.session_type
            )
        )
        session_type_stats = dict(session_type_result.all())

        return {
            "total": total,
            "enabled": enabled,
            "disabled": disabled,
            "by_platform": platform_stats,
            "by_session_type": session_type_stats,
        }

    except Exception as e:
        logger.error(f"获取订阅统计失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取订阅统计失败: {str(e)}")
