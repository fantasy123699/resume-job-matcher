# Backend

`backend/src` 包含 FastAPI API 与 Worker 共享的领域和基础设施代码。`apps/api` 与 `apps/worker` 只保留各自运行入口，禁止复制业务规则。

当前仅提供健康检查和 Worker 生命周期骨架。数据库、账号和业务模型将在后续阶段通过 Alembic 迁移逐步加入。
