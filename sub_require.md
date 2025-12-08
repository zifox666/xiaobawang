# 过滤器条件

## 组成

- 过滤大类
- 类别名称
- 积分倍率

## 基础条件

最低价值 最低为10_000_000 ISK

## 积分计算方案

基础分数为 1

- `基础 * 每个规则叠加 * 服务器折扣 = 最终积分`

## 逻辑

AND/OR

## 过滤大类

- 实体

    | entity | name | 备注 | 积分倍率 |
    |--------|------|------|----------|
    | character | character | 支持 all(final_blow and victim)/final_blow/victim | 1|
    | corporation | corporation | 支持 all(final_blow and victim)/final_blow/victim | 5|
    | alliance | alliance | 支持 all(final_blow and victim)/final_blow/victim | 15|
    | ship | ship | 支持 all(final_blow and victim)/final_blow/victim | 25|
    | system | system | 无子选项 | 15|
    | region | region | 无子选项 | 25|
    | costellation | constellation | 无子选项 | 20|
    | group | group | 无子选项 |20 |

- label

    | 标签 | 名称 | 积分倍率 |
    |------|------|----------|
    | #:1 | #:1 |1 |
    | #:10+ | #:10+ | 1|
    | #:100+ | #:100+ | 1|
    | #:2+ | #:2+ | 1|
    | #:25+ | #:25+ | 1|
    | #:5+ | #:5+ |1 |
    | #:50+ | #:50+ |1 |
    | atShip | atShip | 1|
    | awox | awox |1 |
    | bigisk | bigisk |1 |
    | capital | capital |1 |
    | cat:22 | cat:22 |1 |
    | cat:6 | cat:6 |1 |
    | cat:65 | cat:65 |1 |
    | concord | concord | 1|
    | fw:amamin | fw:amamin |1 |
    | fw:amarr | fw:amarr | 1|
    | fw:calgal | fw:calgal |1 |
    | fw:gallente | fw:gallente | 1|
    | ganked | ganked | 1|
    | isk:10b+ | isk:10b+ | 1|
    | isk:1b+ | isk:1b+ |1 |
    | isk:5b+ | isk:5b+ | 1|
    | loc:abyssal | loc:abyssal |1 |
    | loc:highsec | loc:highsec |1 |
    | loc:lowsec | loc:lowsec |1 |
    | loc:nullsec | loc:nullsec | 1|
    | loc:w-space | loc:w-space |1 |
    | pvp | pvp | 1|
    | solo | solo |1 |
    | tz:au | tz:au | 1|
    | tz:eu | tz:eu |1 |
    | tz:ru | tz:ru |1 |
    | tz:use | tz:use | 1|
    | tz:usw | tz:usw |1 |
    | #:1000+ | #:1000+ |1 |
    | cat:87 | cat:87 | 1|
    | fw:caldari | fw:caldari |1 |
    | fw:minmatar | fw:minmatar | 1|
    | isk:100b+ | isk:100b+ | 1|
    | extremeisk | extremeisk | 1|
    | cat:23 | cat:23 | 1|
    | cat:40 | cat:40 |1 |
    | cat:46 | cat:46 | 1|
    | cat:18 | cat:18 | 1|
    | loc:drifter | loc:drifter |1 |
    | isk:1t+ | isk:1t+ | 1|

- 价值范围

    积分倍率 1 最小-最大

## 额外

高价值击杀模式 最低范围应该是 15_000_000_000 ISK
