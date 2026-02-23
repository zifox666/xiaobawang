## 使用

### 获取 `Session`：

```python
from nonebot_plugin_uninfo import get_session

@matcher.handle()
async def handle(bot: Bot, event: Event):
    session = await get_session(bot, event)
```

或使用依赖注入的形式：

```python
from nonebot_plugin_uninfo import Uninfo, UniSession, Session

@matcher.handle()
async def handle(session: Session = UniSession()):
    ...

@matcher.handle()
async def handle1(session: Uninfo):
    ...
```

### 拉取用户/群组/频道列表：

```python
from nonebot_plugin_uninfo import SceneType, QryItrface

@matcher.handle()
async def handle(interface: QryItrface):
    users = await interface.get_users()
    groups = await interface.get_scenes(SceneType.GROUP)
    members = await interface.get_members(groups[0].type, groups[0].id)
```

### 使用内建的 `Permission`:

```python
from nonebot import on_command
from nonebot_plugin_uninfo import ADMIN

matcher = on_command("inspect", permission=ADMIN())
```

## 模型定义

### `User`

| 属性       | 类型          | 含义    | 备注   |
|----------|-------------|-------|------|
| `id`     | str         | 用户 id |      |
| `name`   | str \| None | 用户名称  |      |
| `nick`   | str \| None | 用户昵称  | 好友备注 |
| `avatar` | str \| None | 用户头像  |      |
| `gender` | str         | 用户性别  |      |

### `Scene`

| 属性       | 类型            | 含义    | 备注                                              |
|----------|---------------|-------|-------------------------------------------------|
| `id`     | str           | 场景 id |                                                 |
| `type`   | SceneType     | 场景类型  | 可分为 `Private`, `Group`, `Guild` 和 `Channel_XXX` |
| `name`   | str \| None   | 场景名称  |                                                 |
| `avatar` | str \| None   | 场景图标  |                                                 |
| `parent` | Scene \| None | 父级场景  | 适用于频道的二级群组场景, 或针对临时会话的来源群组                      |

### `Member`

| 属性          | 类型               | 含义      | 备注                            |
|-------------|------------------|---------|-------------------------------|
| `user`      | User             | 成员的用户信息 |                               |
| `nick`      | str \| None      | 成员昵称    |                               |
| `role`      | str \| None      | 成员角色组   | 当可能存在多个角色组时，此处会使用 level 最高的那个 |
| `mute`      | MuteInfo \| None | 成员禁言信息  |                               |
| `joined_at` | datetime \| None | 成员加入时间  |                               |

### `Session`

| 属性         | 类型             | 含义     | 备注                 |
|------------|----------------|--------|--------------------|
| `self_id`  | str            | 机器人 id |                    |
| `adapter`  | str            | 适配器名称  |                    |
| `scope`    | str            | 适配器范围  | 相比 adapter 更指向实际平台 |
| `scene`    | Scene          | 事件场景   |                    |
| `user`     | User           | 用户信息   |                    |
| `member`   | Member \| None | 成员信息   | 仅适用于群组,频道场景        |
| `operator` | Member \| None | 操作者信息  | 仅适用于群组,频道场景        |

## 示例

```python
from nonebot_plugin_uninfo import Uninfo
from nonebot import on_command

matcher = on_command("inspect", aliases={"查看"}, priority=1)


@matcher.handle()
async def inspect(session: Uninfo):
    texts = [
        f"平台名: {session.adapter} | {session.scope}",
        f"用户ID: {session.user.name + ' | ' if session.user.name else ''}{session.user.id}",
        f"自身ID: {session.self_id}",
        f"事件场景: {session.scene.type.name}",
        f"频道 ID: {session.scene.name + ' | ' if session.scene.name else ''}{session.scene.id}"
    ]
    if session.scene.parent:
        texts.append(f"群组 ID: {session.scene.parent.name + ' | ' if session.scene.parent.name else ''}{session.scene.parent.id}")
    if session.member:
        texts.append(f"成员 ID: {session.member.nick + ' | ' if session.member.nick else ''}{session.member.id}")
    await matcher.send("\n".join(texts))
```
