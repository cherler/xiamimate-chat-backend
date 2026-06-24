"""商品工作台（workspace）domain.

以「一个用户在追的一个品」为主对象，承载：
- brief（产品简报，详情页/内容生产的数据总线）
- evidence（证据数据，证据图/报告画布复用同一份）
- assets（生成的内容资产，如详情页大纲）
- watch / alert（追踪与变更提醒）

该 domain 完全独立、纯增量，受 ``WORKSPACE_FEATURE_ENABLED`` 开关控制是否对外暴露路由。
关闭开关时本模块不参与任何现有请求路径，行为逐字节回退到现状。
"""
