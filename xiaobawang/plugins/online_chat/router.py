from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pathlib import Path
from nonebot import get_bot, logger, get_driver
from nonebot.adapters.onebot.v11 import Bot, Adapter, Event, Message, MessageSegment
from nonebot.adapters.onebot.v11.event import PrivateMessageEvent, Sender
from nonebot.adapters.onebot.v11.exception import ActionFailed
import json
import asyncio
import traceback

router = APIRouter()

# 获取 HTML 目录
html_dir = Path(__file__).parent / "html"


@router.get("/")
async def chat_page():
    """返回在线聊天室页面"""
    return FileResponse(html_dir / "index.html")


@router.get("/static/{file_name}")
async def serve_static(file_name: str):
    """提供静态文件"""
    file_path = html_dir / file_name
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path)
    return {"error": "File not found"}


@router.get("/get_cmds")
async def get_commands():
    """获取所有可用命令"""
    from arclet.alconna import command_manager
    
    commands = []
    for cmd in command_manager.get_commands():
        commands.append({
            "cmd": f"/{cmd.name}",
            "usage": cmd.meta.usage or "",
            "description": cmd.meta.description or ""
        })
    
    return commands


# 存储 WebSocket 连接 {user_id: {"ws": websocket, "bot": virtual_bot}}
websocket_connections = {}

# 存储 API 请求的 Future {echo: {"future": Future, "ws": websocket}}
api_futures = {}


class VirtualBot(Bot):
    """虚拟 Bot,用于聊天室,不连接真实 OneBot 服务"""
    
    def __init__(self, self_id: str, websocket: WebSocket):
        # 获取 OneBot v11 适配器
        driver = get_driver()
        adapter = None
        for adp in driver._adapters.values():
            if isinstance(adp, Adapter):
                adapter = adp
                break
        
        if not adapter:
            raise RuntimeError("未找到 OneBot v11 适配器")
        
        super().__init__(adapter, self_id)
        self.websocket = websocket
    
    async def send(self, event: Event, message, **kwargs):
        """发送消息到前端"""
        logger.info(f"虚拟 Bot {self.self_id} 发送消息: {message}")
        
        # 转换消息为消息段数组
        message_segments = []
        if isinstance(message, str):
            parsed_msg = Message(message)
            for seg in parsed_msg:
                message_segments.append({
                    "type": seg.type,
                    "data": seg.data
                })
        elif isinstance(message, Message):
            for seg in message:
                message_segments.append({
                    "type": seg.type,
                    "data": seg.data
                })
        else:
            message_segments.append({
                "type": "text",
                "data": {"text": str(message)}
            })
        
        # 生成唯一的 echo
        import uuid
        echo = str(uuid.uuid4())
        
        # 创建 Future 等待响应
        future = asyncio.Future()
        api_futures[echo] = {
            "future": future,
            "ws": self.websocket
        }
        
        # 发送到前端
        try:
            await self.websocket.send_text(json.dumps({
                "action": "send_msg",
                "params": {
                    "user_id": event.user_id if hasattr(event, 'user_id') else 0,
                    "message": message_segments
                },
                "echo": echo
            }))
            
            logger.info(f"发送 send_msg 到前端,echo: {echo}")
            
            # 等待响应,超时 5 秒
            try:
                response = await asyncio.wait_for(future, timeout=5.0)
                logger.info(f"收到前端响应: {response}")
                
                # 返回消息 ID
                if response.get("status") == "ok":
                    message_id = response.get("data", {}).get("message_id", 0)
                    return {"message_id": message_id}
                else:
                    return {"message_id": 0}
            except asyncio.TimeoutError:
                logger.warning(f"等待前端响应超时: {echo}")
                return {"message_id": 0}
        except Exception as e:
            logger.error(f"发送消息到前端失败: {e}")
            return {"message_id": 0}
        finally:
            # 清理 Future
            api_futures.pop(echo, None)
    
    async def call_api(self, api: str, **data):
        """处理 API 调用"""
        logger.info(f"虚拟 Bot {self.self_id} 调用 API: {api}, 参数: {data}")
        
        if api == "get_msg":
            # 通过 WebSocket 向前端请求消息
            message_id = data.get("message_id")
            
            # 生成唯一的 echo
            import uuid
            echo = str(uuid.uuid4())
            
            # 创建 Future 等待响应
            future = asyncio.Future()
            api_futures[echo] = {
                "future": future,
                "ws": self.websocket
            }
            
            try:
                # 向前端发送 get_msg 请求
                await self.websocket.send_text(json.dumps({
                    "action": "get_msg",
                    "params": {
                        "message_id": message_id
                    },
                    "echo": echo
                }))
                
                logger.info(f"向前端发送 get_msg 请求: {message_id}, echo: {echo}")
                
                # 等待响应,超时 5 秒
                try:
                    response = await asyncio.wait_for(future, timeout=5.0)
                    logger.info(f"收到前端响应: {response}")
                    
                    # 检查响应状态
                    if response.get("status") == "ok":
                        return response.get("data")
                    else:
                        raise ActionFailed(
                            status="failed",
                            retcode=response.get("retcode", 1404),
                            data=response.get("data", {"message": "消息不存在"}),
                            echo=""
                        )
                except asyncio.TimeoutError:
                    logger.warning(f"等待前端响应超时: {echo}")
                    raise ActionFailed(
                        status="failed",
                        retcode=1404,
                        data={"message": "请求超时"},
                        echo=""
                    )
            finally:
                # 清理 Future
                api_futures.pop(echo, None)
        
        # 其他 API 返回默认值
        return {}


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 端点 - 使用虚拟 Bot"""
    await websocket.accept()
    user_id = None
    virtual_bot = None
    
    try:
        while True:
            # 接收来自前端的消息
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            logger.info(f"收到网页消息: {message_data}")
            
            # 如果是 API 响应
            if "echo" in message_data and message_data.get("echo") in api_futures:
                echo = message_data["echo"]
                future_data = api_futures.get(echo)
                if future_data and not future_data["future"].done():
                    future_data["future"].set_result(message_data)
                continue
            
            # 如果是消息事件
            if message_data.get("post_type") == "message":
                user_id = message_data.get("user_id")
                
                try:
                    # 创建或获取虚拟 Bot
                    if user_id not in websocket_connections:
                        virtual_bot = VirtualBot(self_id=f"chat_{user_id}", websocket=websocket)
                        websocket_connections[user_id] = {
                            "ws": websocket,
                            "bot": virtual_bot
                        }
                    else:
                        virtual_bot = websocket_connections[user_id]["bot"]
                    
                    # 将消息段字典转换为 MessageSegment 对象
                    message_list = []
                    for seg in message_data.get("message", []):
                        seg_type = seg.get("type")
                        seg_data = seg.get("data", {})
                        
                        if seg_type == "text":
                            message_list.append(MessageSegment.text(seg_data.get("text", "")))
                        elif seg_type == "image":
                            message_list.append(MessageSegment.image(seg_data.get("file", "")))
                        elif seg_type == "reply":
                            message_list.append(MessageSegment.reply(seg_data.get("id", "")))
                    
                    # 构造 Message 对象
                    message = Message(message_list)
                    
                    # 构造 PrivateMessageEvent
                    message_id = message_data.get("message_id")
                    event = PrivateMessageEvent(
                        time=message_data.get("time"),
                        self_id=int(virtual_bot.self_id.split('_')[1]),
                        post_type="message",
                        sub_type=message_data.get("sub_type", "friend"),
                        user_id=user_id,
                        message_type="private",
                        message_id=message_id,
                        message=message,
                        raw_message=message_data.get("raw_message", ""),
                        font=message_data.get("font", 0),
                        sender=Sender(**message_data.get("sender", {}))
                    )
                    
                    logger.info(f"构造的事件对象 message: {event.message}, raw_message: {event.raw_message}")
                    
                    # 处理事件
                    asyncio.create_task(virtual_bot.handle_event(event))
                    
                except Exception as e:
                    logger.error(f"处理消息失败: {e}", exc_info=True)
                    await websocket.send_text(json.dumps({
                        "action": "send_msg",
                        "params": {
                            "message": f"处理失败: {str(e)}"
                        }
                    }))
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket 连接断开: {user_id}")
        if user_id and user_id in websocket_connections:
            del websocket_connections[user_id]
    except Exception as e:
        logger.error(f"WebSocket 错误: {traceback.format_exc()}", exc_info=True)
        if user_id and user_id in websocket_connections:
            del websocket_connections[user_id]
