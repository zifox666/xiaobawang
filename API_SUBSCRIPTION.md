## 订阅 (Subscription) API 文档

### 基础信息

- **前缀**: `/sub`
- **内容类型**: `application/json`
- **认证**: 无（开发阶段）

---

## API 端点

### 1. 获取订阅列表

**请求**
```
GET /sub
```

**查询参数**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| page | integer | 否 | 页码 (默认: 1) |
| page_size | integer | 否 | 每页数量 (默认: 20, 最大: 100) |
| platform | string | 否 | 平台过滤 (如: qq, telegram) |
| bot_id | string | 否 | 机器人ID过滤 |
| session_id | string | 否 | 会话ID过滤 |
| is_enabled | boolean | 否 | 启用状态过滤 |

**响应 (200 OK)**
```json
{
  "total": 100,
  "page": 1,
  "page_size": 20,
  "data": [
    {
      "id": 1,
      "name": "高价值击杀",
      "description": "监控所有10亿以上的击杀",
      "platform": "qq",
      "bot_id": "1234567890",
      "session_id": "123456789",
      "session_type": "group",
      "min_value": 1000000000,
      "max_age_days": null,
      "is_enabled": true,
      "condition_groups": {
        "logic": "AND",
        "conditions": []
      },
      "created_at": "2025-12-08T10:00:00",
      "updated_at": "2025-12-08T10:00:00"
    }
  ]
}
```

**示例**
```bash
# 获取第1页，每页20条
curl "http://localhost:8000/sub"

# 获取QQ平台的订阅
curl "http://localhost:8000/sub?platform=qq"

# 获取启用的订阅
curl "http://localhost:8000/sub?is_enabled=true"

# 综合查询
curl "http://localhost:8000/sub?platform=qq&bot_id=123456&page=2&page_size=50"
```

---

### 2. 获取订阅详情

**请求**
```
GET /sub/{sub_id}
```

**路径参数**
| 参数 | 类型 | 说明 |
|------|------|------|
| sub_id | integer | 订阅ID |

**响应 (200 OK)**
```json
{
  "id": 1,
  "name": "高价值击杀",
  "description": "监控所有10亿以上的击杀",
  "platform": "qq",
  "bot_id": "1234567890",
  "session_id": "123456789",
  "session_type": "group",
  "min_value": 1000000000,
  "max_age_days": null,
  "is_enabled": true,
  "condition_groups": {
    "logic": "AND",
    "conditions": []
  },
  "created_at": "2025-12-08T10:00:00",
  "updated_at": "2025-12-08T10:00:00"
}
```

**错误响应 (404 Not Found)**
```json
{
  "detail": "订阅 1 不存在"
}
```

**示例**
```bash
curl "http://localhost:8000/sub/1"
```

---

### 3. 创建订阅

**请求**
```
POST /sub
```

**请求体**
```json
{
  "name": "高价值击杀",
  "description": "监控所有10亿以上的击杀",
  "platform": "qq",
  "bot_id": "1234567890",
  "session_id": "123456789",
  "session_type": "group",
  "min_value": 1000000000,
  "max_age_days": null,
  "condition_groups": {
    "logic": "AND",
    "conditions": []
  }
}
```

**字段说明**
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 是 | 订阅名称 |
| description | string | 否 | 描述 |
| platform | string | 是 | 平台 (qq/telegram等) |
| bot_id | string | 是 | 机器人ID |
| session_id | string | 是 | 会话ID (群号/频道ID等) |
| session_type | string | 是 | 会话类型 (group/private等) |
| min_value | float | 否 | 最低价值 (默认: 100000000) |
| max_age_days | integer | 否 | 最大天数 (可选) |
| condition_groups | object | 是 | 条件配置 |

**响应 (200 OK)**
```json
{
  "success": true,
  "message": "订阅创建成功",
  "data": {
    "sub_id": 42
  }
}
```

**错误响应 (400 Bad Request)**
```json
{
  "detail": "创建订阅失败"
}
```

**示例 - 简单高价值订阅**
```bash
curl -X POST "http://localhost:8000/sub" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "高价值击杀",
    "platform": "qq",
    "bot_id": "1234567890",
    "session_id": "123456789",
    "session_type": "group",
    "min_value": 1000000000,
    "condition_groups": {
      "logic": "AND",
      "conditions": []
    }
  }'
```

**示例 - 复杂条件订阅**
```bash
curl -X POST "http://localhost:8000/sub" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "虫洞PVP",
    "description": "虫洞中的高价值战斗",
    "platform": "qq",
    "bot_id": "1234567890",
    "session_id": "123456789",
    "session_type": "group",
    "min_value": 500000000,
    "condition_groups": {
      "logic": "AND",
      "conditions": [
        {
          "type": "location",
          "location_type": "wormhole",
          "location_name": "虫洞"
        },
        {
          "type": "label",
          "required_labels": ["capital"],
          "excluded_labels": ["awox"]
        }
      ]
    }
  }'
```

---

### 4. 更新订阅

**请求**
```
PUT /sub/{sub_id}
```

**路径参数**
| 参数 | 类型 | 说明 |
|------|------|------|
| sub_id | integer | 订阅ID |

**请求体** (所有字段可选)
```json
{
  "name": "新的名称",
  "description": "新的描述",
  "min_value": 2000000000,
  "max_age_days": 10,
  "is_enabled": false,
  "condition_groups": {
    "logic": "AND",
    "conditions": []
  }
}
```

**响应 (200 OK)**
```json
{
  "success": true,
  "message": "订阅更新成功",
  "data": null
}
```

**示例**
```bash
# 只更新名称
curl -X PUT "http://localhost:8000/sub/1" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "新的订阅名称"
  }'

# 禁用订阅
curl -X PUT "http://localhost:8000/sub/1" \
  -H "Content-Type: application/json" \
  -d '{
    "is_enabled": false
  }'

# 更新条件
curl -X PUT "http://localhost:8000/sub/1" \
  -H "Content-Type: application/json" \
  -d '{
    "condition_groups": {
      "logic": "AND",
      "conditions": [
        {
          "type": "value",
          "min": 2000000000
        }
      ]
    }
  }'
```

---

### 5. 删除订阅

**请求**
```
DELETE /sub/{sub_id}
```

**路径参数**
| 参数 | 类型 | 说明 |
|------|------|------|
| sub_id | integer | 订阅ID |

**响应 (200 OK)**
```json
{
  "success": true,
  "message": "订阅删除成功",
  "data": null
}
```

**错误响应 (404 Not Found)**
```json
{
  "detail": "订阅 1 不存在"
}
```

**示例**
```bash
curl -X DELETE "http://localhost:8000/sub/1"
```

---

### 6. 获取订阅模板

**请求**
```
GET /sub/templates/{template_name}
```

**路径参数**
| 参数 | 类型 | 说明 |
|------|------|------|
| template_name | string | 模板名称 |

**可用模板**
- `high_value` - 高价值击杀
- `alliance_loss` - 联盟损失
- `wormhole_label` - 虫洞PVP
- `capital_loss` - 旗舰损失
- `f1_heavy` - F1战士重战
- `nullsec_fight` - 00战斗
- `supercap_vs_goons` - 超旗VS Goons
- `faction_war` - 阵营战争

**响应 (200 OK)**
```json
{
  "name": "高价值击杀",
  "description": "简单的高价值订阅,仅按价值过滤",
  "config": {
    "logic": "AND",
    "conditions": []
  }
}
```

**示例**
```bash
# 获取高价值模板
curl "http://localhost:8000/sub/templates/high_value"

# 获取虫洞模板
curl "http://localhost:8000/sub/templates/wormhole_label"
```

---

### 7. 获取所有模板列表

**请求**
```
GET /sub/templates
```

**响应 (200 OK)**
```json
{
  "high_value": {
    "name": "高价值击杀",
    "description": "简单的高价值订阅,仅按价值过滤",
    "config": {...}
  },
  "alliance_loss": {
    "name": "联盟损失",
    "description": "监控特定联盟的所有损失",
    "config": {...}
  },
  ...
}
```

**示例**
```bash
curl "http://localhost:8000/sub/templates"
```

---

### 8. 获取订阅统计

**请求**
```
GET /sub/stats/summary
```

**响应 (200 OK)**
```json
{
  "total": 100,
  "enabled": 85,
  "disabled": 15,
  "by_platform": {
    "qq": 60,
    "telegram": 40
  },
  "by_session_type": {
    "group": 80,
    "private": 20
  }
}
```

**示例**
```bash
curl "http://localhost:8000/sub/stats/summary"
```

---

## 条件配置说明

### 条件类型

#### 1. Entity (实体条件)
```json
{
  "type": "entity",
  "entity_type": "alliance",  // character/corporation/alliance/faction等
  "entity_id": 1354830081,
  "entity_name": "Goonswarm",
  "role": "victim"             // victim/final_blow/any_attacker
}
```

#### 2. Location (位置条件)
```json
{
  "type": "location",
  "location_type": "wormhole",  // wormhole/region/system
  "location_id": 10000060,
  "location_name": "Delve"
}
```

#### 3. Ship (舰船条件)
```json
{
  "type": "ship",
  "ship_type_id": 587,
  "ship_category": "capital",      // capital/supercapital
  "ship_role": "victim_ship",      // victim_ship/final_blow_ship
  "ship_name": "Rifter"
}
```

#### 4. Value (价值条件)
```json
{
  "type": "value",
  "min": 100000000,
  "max": 1000000000
}
```

#### 5. Label (标签条件)
```json
{
  "type": "label",
  "required_labels": ["loc:nullsec", "tz:eu"],
  "excluded_labels": ["awox"]
}
```

#### 6. Stats (战斗统计条件)
```json
{
  "type": "stats",
  "ships_destroyed_min": 50,
  "danger_ratio_min": 40,
  "solo_kills_min": 5
}
```

### 逻辑组合

#### AND 逻辑 (所有条件都满足)
```json
{
  "logic": "AND",
  "conditions": [
    {"type": "entity", ...},
    {"type": "value", ...}
  ]
}
```

#### OR 逻辑 (至少一个条件满足)
```json
{
  "logic": "OR",
  "groups": [
    {
      "logic": "AND",
      "conditions": [...]
    },
    {
      "logic": "AND",
      "conditions": [...]
    }
  ]
}
```

#### 嵌套逻辑 (无限深度)
```json
{
  "logic": "AND",
  "conditions": [...],
  "groups": [
    {
      "logic": "OR",
      "conditions": [...],
      "groups": [...]
    }
  ]
}
```

---

## 常见用例

### 1. 简单高价值订阅 (>10亿ISK)
```json
{
  "name": "高价值击杀",
  "platform": "qq",
  "bot_id": "123",
  "session_id": "456",
  "session_type": "group",
  "min_value": 1000000000,
  "condition_groups": {
    "logic": "AND",
    "conditions": []
  }
}
```

### 2. 监控特定联盟的所有损失
```json
{
  "name": "GSF损失监控",
  "platform": "qq",
  "bot_id": "123",
  "session_id": "456",
  "session_type": "group",
  "min_value": 100000000,
  "condition_groups": {
    "logic": "AND",
    "conditions": [
      {
        "type": "entity",
        "entity_type": "alliance",
        "entity_id": 1354830081,
        "entity_name": "Goonswarm Federation",
        "role": "victim"
      }
    ]
  }
}
```

### 3. 虫洞高价值战斗
```json
{
  "name": "虫洞PVP",
  "platform": "qq",
  "bot_id": "123",
  "session_id": "456",
  "session_type": "group",
  "min_value": 500000000,
  "condition_groups": {
    "logic": "AND",
    "conditions": [
      {
        "type": "location",
        "location_type": "wormhole",
        "location_name": "虫洞"
      },
      {
        "type": "label",
        "required_labels": ["capital"],
        "excluded_labels": ["awox"]
      }
    ]
  }
}
```

### 4. 旗舰击杀 OR 联盟损失
```json
{
  "name": "旗舰战报",
  "platform": "qq",
  "bot_id": "123",
  "session_id": "456",
  "session_type": "group",
  "min_value": 1000000000,
  "condition_groups": {
    "logic": "OR",
    "groups": [
      {
        "logic": "AND",
        "conditions": [
          {
            "type": "ship",
            "ship_category": "capital",
            "ship_role": "victim_ship"
          }
        ]
      },
      {
        "logic": "AND",
        "conditions": [
          {
            "type": "entity",
            "entity_type": "alliance",
            "entity_id": 1354830081,
            "entity_name": "GSF",
            "role": "victim"
          }
        ]
      }
    ]
  }
}
```

---

## 错误处理

### HTTP 状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 请求错误 |
| 404 | 资源不存在 |
| 500 | 服务器错误 |

### 错误响应格式
```json
{
  "detail": "错误信息描述"
}
```

---

## 测试工具

### 使用 curl
```bash
# 获取列表
curl "http://localhost:8000/sub"

# 创建订阅
curl -X POST "http://localhost:8000/sub" \
  -H "Content-Type: application/json" \
  -d '{"name":"test","platform":"qq",...}'

# 更新订阅
curl -X PUT "http://localhost:8000/sub/1" \
  -H "Content-Type: application/json" \
  -d '{"name":"new_name"}'

# 删除订阅
curl -X DELETE "http://localhost:8000/sub/1"
```

### 使用 Python requests
```python
import requests

base_url = "http://localhost:8000"

# 获取列表
response = requests.get(f"{base_url}/sub")
print(response.json())

# 创建订阅
data = {
    "name": "高价值击杀",
    "platform": "qq",
    "bot_id": "123",
    "session_id": "456",
    "session_type": "group",
    "condition_groups": {"logic": "AND", "conditions": []}
}
response = requests.post(f"{base_url}/sub", json=data)
print(response.json())
```

### 使用 FastAPI Swagger UI
访问 `http://localhost:8000/docs` 可以看到交互式API文档

---

## 注意事项

1. **条件配置**: 必须是有效的JSON，否则会被转换为空字典
2. **分页**: page 从 1 开始，page_size 最大 100
3. **平台字符串**: 建议使用小写 (如 "qq", "telegram")
4. **Entity ID**: 必须是有效的EVE Online ID
5. **缓存**: 创建/更新/删除后会自动清除缓存
6. **并发**: API支持异步并发请求

---

## 后续规划

- [ ] 添加认证和权限控制
- [ ] 前端网页界面
- [ ] 订阅验证和预览功能
- [ ] 订阅复制/导出功能
- [ ] 批量操作支持
- [ ] 订阅历史和审计日志
