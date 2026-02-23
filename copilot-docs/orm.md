## 使用方式

### ORM

#### Model 依赖注入

```python
from nonebot.adapters import Event
from nonebot.params import Depends
from nonebot import require, on_message
from sqlalchemy.orm import Mapped, mapped_column

require("nonebot_plugin_orm")
from nonebot_plugin_orm import Model, async_scoped_session

matcher = on_message()


def get_user_id(event: Event) -> str:
    return event.get_user_id()


class User(Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = Depends(get_user_id)


@matcher.handle()
async def _(event: Event, sess: async_scoped_session, user: User | None):
    if user:
        await matcher.finish(f"Hello, {user.user_id}")

    sess.add(User(user_id=get_user_id(event)))
    await sess.commit()
    await matcher.finish("Hello, new user!")
```

#### SQL 依赖注入

```python
from sqlalchemy import select
from nonebot.adapters import Event
from nonebot.params import Depends
from nonebot import require, on_message
from sqlalchemy.orm import Mapped, mapped_column

require("nonebot_plugin_orm")
from nonebot_plugin_orm import Model, SQLDepends, async_scoped_session

matcher = on_message()


def get_session_id(event: Event) -> str:
    return event.get_session_id()


class Session(Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str]


@matcher.handle()
async def _(
    event: Event,
    sess: async_scoped_session,
    session: Session
    | None = SQLDepends(
        select(Session).where(Session.session_id == Depends(get_session_id))
    ),
):
    if session:
        await matcher.finish(f"Hello, {session.session_id}")

    sess.add(Session(session_id=get_session_id(event)))
    await sess.commit()
    await matcher.finish("Hello, new user!")

```

### CLI

依赖 [NB CLI](https://github.com/nonebot/nb-cli)

```properties
$ nb orm
Usage: nb orm [OPTIONS] COMMAND [ARGS]...

Options:
  -c, --config FILE  可选的配置文件；默认为 ALEMBIC_CONFIG 环境变量的值，或者 "alembic.ini"（如果存在）
  -n, --name TEXT    .ini 文件中用于 Alembic 配置的小节的名称  [default: alembic]
  -x TEXT            自定义 env.py 脚本使用的其他参数，例如：-x setting1=somesetting -x
                     setting2=somesetting
  -q, --quite        不要输出日志到标准输出
  --help             Show this message and exit.

Commands:
  branches        显示所有的分支。
  check           检查数据库是否与模型定义一致。
  current         显示当前的迁移。
  downgrade       回退到先前版本。
  edit            使用 $EDITOR 编辑迁移脚本。
  ensure_version  创建版本表。
  heads           显示所有的分支头。
  history         显示迁移的历史。
  init            初始化脚本目录。
  list_templates  列出所有可用的模板。
  merge           合并多个迁移。创建一个新的迁移脚本。
  revision        创建一个新迁移脚本。
  show            显示迁移的信息。
  stamp           将数据库标记为特定的迁移版本，不运行任何迁移。
  upgrade         升级到较新版本。
```