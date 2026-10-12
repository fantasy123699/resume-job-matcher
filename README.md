# Resume Job Matcher

面向中国大陆程序员求职者的开源 Web 工具：从用户确认的简历事实出发，分析目标 JD，并在不捏造经历、技能或数据的前提下生成可审核的简历优化建议。

项目工程规则见 [PROJECT_RULES.md](PROJECT_RULES.md)。该文档优先于普通开发习惯：首版不登录招聘平台、不绕过访问控制、不自动投递，所有事实性修改都需要用户审批。

## 当前状态

JD 与匹配阶段进行中。后端已有邀请码认证、邮箱验证/找回密码、简历导入与事实确认；现在支持用户粘贴 JD，提取原文中出现的技术要求/加分项，并只用已确认的原子技能事实进行可解释匹配。未在简历中找到证据的要求只标记为“当前无证据”。每一份匹配结果都会以“简历版本 + JD + 算法版本”保存为快照，后续更新主简历不会改写旧记录。首个修改建议接口只会生成基于已确认匹配技能的“技能区段前置”建议，保留原文、不改写事实，并要求用户逐条接受或拒绝。

## 技术栈

- Next.js + TypeScript：前端
- FastAPI + Pydantic：公开业务 API
- Python Worker：异步任务和后续 Agent
- PostgreSQL：唯一业务数据与任务持久化存储
- Docker Compose + Caddy：单机部署基线

## 本地前置条件

- Node.js 24（或项目锁定版本要求的兼容版本）
- pnpm 11
- Python 3.13
- uv
- Docker Desktop（运行 PostgreSQL 和完整容器环境时需要）

## 本地启动

1. 复制 `.env.example` 为 `.env`，仅填入本地开发值。
2. 安装前端依赖：`pnpm install`。
3. 安装后端依赖：`uv --directory backend sync --all-groups`。
4. 启动数据库：`docker compose --env-file .env -f deploy/compose.yaml -f deploy/compose.dev.yaml up db`。
5. 执行迁移：`uv --directory backend run alembic upgrade head`。
6. 初始化首个管理员：`uv --directory backend run python -m resume_job_matcher.cli create-admin --email your-email@example.com`。
7. 生成首个邀请码：`uv --directory backend run python -m resume_job_matcher.cli create-invitation --admin-email your-email@example.com`。邀请码只显示一次，应通过安全渠道保存和发放。
8. 启动 API：`uv --directory backend run uvicorn --app-dir ../apps/api main:app --reload --port 8000`。
9. 启动 Web：`pnpm dev:web`。
10. 可选启动 Worker：`uv --directory backend run python ../apps/worker/main.py`。

`.env` 中的 `SESSION_SECRET` 必须替换为至少 32 个字符的随机值；API 会拒绝使用示例占位符启动。生产环境的 `WEB_ORIGIN` 必须是正式 HTTPS 域名。`/health/ready` 会实际检查 PostgreSQL 连接。

邮箱验证与找回密码使用 QQ SMTP。生产环境请设置 `MAIL_PROVIDER=qq_smtp`，并填写 `MAIL_FROM`、`MAIL_SMTP_USERNAME`、`MAIL_SMTP_AUTHORIZATION_CODE`。授权码需在 QQ 邮箱中单独生成，不能填写邮箱登录密码，也不要提交到仓库或发送到聊天。验证与重置链接把一次性令牌放在 URL 片段中，前端会将其作为 POST 请求体提交，避免令牌进入常见的访问日志查询参数。

前端入口为 `/`、`/register`、`/login`、`/verify-email`、`/reset-password`、`/resumes`、`/jobs` 和 `/history`。`/` 工作台只显示当前账户的真实进度与最近记录；`/resumes` 提供文本或文件导入、逐条确认/修正/拒绝事实及最终确认主简历的界面；`/jobs` 支持粘贴 JD、查看原文要求与简历事实的逐项证据、接受或拒绝低风险的重排建议，并在所有建议已完成审核后生成不可变版本和下载 DOCX；`/history` 可回访保存的 JD、匹配快照与版本。生成版本必须提交幂等键，同一用户重复提交同一键会返回同一版本。上述页面都必须先登录。本地将 Web 与 API 分别运行在 3000、8000 端口时，把 `NEXT_PUBLIC_API_BASE_URL` 设置为 `http://localhost:8000`；通过 Caddy 以同源方式运行时保持为空。验证与重设令牌只可使用一次，重设成功后所有旧会话都会被撤销。

简历导入接口为 `POST /api/v1/resumes/import`：在带 CSRF Header 的登录会话中提交 `text_content`，或提交一个 `file`（`.pdf`、`.docx`、UTF-8 `.txt`，最多 5 MB）。上传二进制只写入操作系统临时目录，解析成功或失败后都会删除；扫描版或无文本 PDF 会被拒绝。使用 `GET /api/v1/resumes` 查看自己的简历列表，使用 `GET /api/v1/resumes/{id}` 查看事实，并逐条调用 `PATCH /api/v1/resumes/{id}/facts/{fact_id}` 审核，再调用 `POST /api/v1/resumes/{id}/confirm` 确认。

JD 接口为 `POST /api/v1/jobs/from-text`，提交 `title` 和 `content`；结果包含从原文中提取的技术要求、加分项和原文位置。确认主简历后，调用带 CSRF Header 的 `POST /api/v1/matches` 并提交 `resume_profile_id` 与 `job_description_id`，即可创建或读取同一算法版本下的匹配快照，结果包含 `satisfied` 与 `no_evidence` 两组逐项证据。通过 `GET /api/v1/jobs/{job_id}/matches` 可读取该 JD 的历史快照。该接口不生成录用概率，也不会修改简历事实。

调用 `POST /api/v1/optimizations` 并提交相同的两个 ID，可得到可追溯的修改建议；可用 `GET /api/v1/optimizations?resume_profile_id=...&job_description_id=...` 读取同一简历和 JD 对应的历史建议。每条建议包含原文、拟议文本、修改类型、理由、关联的 `resume_fact_ids` 与 `job_requirement_ids`、风险级别及审批状态。首版目前仅允许不改变语义的 `reorder` 建议；调用 `PATCH /api/v1/optimizations/{suggestion_id}` 并提交 `accepted` 或 `rejected` 后，才会记录用户决定。它不会直接改动主简历。

用户可以调用 `POST /api/v1/resume-versions` 生成一个不可变的、面向指定 JD 的简历版本快照；版本只包含已确认或用户修正的区段事实。已接受的建议仅影响区段排序，待处理或被拒绝的建议不会进入版本。`GET /api/v1/resume-versions/{version_id}` 只能由版本所有者读取。

调用 `POST /api/v1/resume-versions/{version_id}/exports/docx` 会从该版本快照生成一份中文、ATS 友好的 DOCX，并返回受鉴权保护的下载地址。导出文件保留 24 小时；API 在创建导出时清理过期文件，Worker 每小时再执行一次清理。Compose 使用独立持久卷保存这些短期文件。PDF 导出仍未实现。

账号删除接口为 `POST /api/v1/auth/account/deletion`，需在已登录会话中提交当前密码及确认词 `DELETE`。提交后账号会立即冻结、所有会话被撤销，Worker 在 7 天等待期结束后清除活跃业务数据和短期导出文件。

`POST /api/v1/agent-runs` 可为一份已确认的简历和已保存 JD 创建可恢复的优化任务。Worker 会生成已有的低风险建议并把任务推进至 `WAIT_USER_APPROVE_EDITS`，同时持久化审批检查点。所有建议完成逐项接受或拒绝后，用户才能调用 `POST /api/v1/agent-runs/{run_id}/approval` 完成或取消任务。该基础状态机尚未接入模型、岗位搜索或任何招聘平台。

容器部署时，必须在更新 API 前由运维人员显式执行迁移，不能让应用启动时自动改表：

```text
docker compose --env-file .env -f deploy/compose.yaml run --rm api alembic -c /app/backend/alembic.ini upgrade head
```

## 验证命令

```text
pnpm check:web
uv --directory backend run ruff check .
uv --directory backend run ruff format --check .
uv --directory backend run mypy src ../apps/api ../apps/worker
uv --directory backend run pytest
```

## 秋招岗位公开页面监控

仓库包含一个独立的一次性监控脚本，可对已审核登记的政府、高校和企业官方公开招聘页执行 JD 关键词筛选、去重并生成每日 Markdown/CSV。它不会登录招聘平台或自动投递。配置来源、运行命令与 Windows 每日计划任务见 [docs/JOB_WATCH.md](docs/JOB_WATCH.md)。

## 部署边界

生产部署、云资源创建、域名解析、备案和外部服务密钥录入均需要项目所有者明确授权。生产环境必须用真实域名覆盖 `.env` 中的 `APP_DOMAIN`，并完成 Preview 验证、数据库备份恢复演练和生产冒烟测试。

## 开源贡献

当前阶段只接受 Issue，不接受代码 PR。请勿在 Issue 中提交真实简历、Cookie、密码、API Key 或招聘平台凭据。详见 [CONTRIBUTING.md](CONTRIBUTING.md) 和 [SECURITY.md](SECURITY.md)。
