# EVE Online ESI 授权管理器

## 介绍

通过该模块 对整体用户授权获取esi token进行管理，提供了一个接口来获取用户的授权信息，和access_token

## 功能

1. 其他服务申请一个具体需要访问的用户权限
2. 构造oauth链接scopes，交给用户授权本模块访问指定范围
3. 用户授权后，获取refresh_token到数据库，access_token到redis
4. 数据库需要记录用户的character_id，refresh_token，授权范围scopes，授权时间等信息
5. 定期检查access_token的有效性，过期后使用refresh_token刷新获取新的access_token
6. 提供接口查询用户的授权信息和当前有效的access_token
7. 在[scope.json](./src/scopes.json)提供了为用户可选/必选的授权列表，按照客户意愿增量授权范围，减少用户授权负担

## 要求

1. 重要内容精简在本文档后面
2. 只保留必要注释
3. orm请使用nonebot-plugin-orm，参考方法在[core](../core/helper)中
4. 新建一个plugins目录下的cache模块 专门提供全局的cache服务 之前已有的cache暂时不进行修改 本服务使用新cache 原有cache参考[cache](../core/utils/common/cache.py)
5. API接口请使用POST方法，不要采用restful，返回应`{code,data,msg}`
6. 前端使用tailwindcss，保证暗色模式
7. config请参照[config](xiaobawang/plugins/core/config.py)设置oauth所必须的配置 prex用esi_oauth
