# 端到端工作流程

> 配套 `docs/PROJECT_BLOCKS.md`：那份讲"有哪些块"，这份讲"块怎么串起来"。
> 所有步骤均对照源码核实，标注了实际写入的数据表与所处块。

## 一、三层架构与职责

| 进程 | 技术 | 职责 | 不做 |
| --- | --- | --- | --- |
| **Web** | Next.js + TypeScript | 工作台交互、逐条审批 UI、下载 | 不直接访问数据库 |
| **API** | FastAPI + Pydantic | 同步业务逻辑、鉴权、数据读写 | 不做长耗时任务（会被 Caddy 超时切断） |
| **Worker** | Python | 异步任务、定时清理、公开来源采集 | 不接 HTTP 请求 |
| **PostgreSQL** | 唯一持久化 | 业务数据 + 任务队列（`FOR UPDATE SKIP LOCKED`） | —— |

---

## 二、主流程（9 步）

```
[1] 注册/登录 ──> [2] 导入简历 ──> [3] 事实确认 ⛔ ──> [4] 粘贴 JD
                     (B)              (B) 人工闸门        (C)
                                                          │
[9] 投递追踪 <── [8] 版本+导出 <── [7] 逐条审批 ⛔ <── [6] 建议生成 <── [5] 匹配
     (F)❌          (E)✅              (E) 硬闸门         (E)          (D)
```

### [1] 注册与登录 —— A 块 ✅

- **动作**：`POST /auth/register`（邀请码 + 邮箱 + 密码 + 成年确认）→ `POST /auth/email-verification/*` → `POST /auth/login`
- **写入**：`users`、`invitations`、`sessions`、`email_verification_tokens`、`auth_rate_limits`
- **安全**：CSRF Header、登录限流、会话轮换与撤销

### [2] 导入简历 —— B 块 ⚠️

- **动作**：`POST /resumes/import`，提交 `text_content` 或 `file`（PDF/DOCX/UTF-8 TXT，≤5MB）
- **内部**：
  1. `determine_file_format` → `extract_source_lines`（PyMuPDF / python-docx / 纯文本）
  2. 二进制只写系统临时目录，**解析成功或失败后都删除**
  3. `build_facts`：`classify_heading` 按 13 项中文标题字典切段 → `extract_skill_facts`
  4. 技能抽取走 202 项分类词典（`find_technology_mentions`）
- **写入**：`resume_profiles`（`parser_version = deterministic-facts-v3`）+ `resume_facts`（`user_status = pending`）
- **⚠️ 内核缺口**：`page.get_text("text")` 丢掉了字号/加粗/坐标；DOCX 丢掉了 `style.name`。**纯文本行扫描**，双栏/页眉页脚/表格都处理不了

### [3] 事实确认（人工闸门 ⛔）—— B 块 ✅

- **动作**：`GET /resumes/{id}` 查看 → `PATCH /resumes/{id}/facts/{fact_id}` 逐条 `confirmed` / `user_corrected` / `rejected` → `POST /resumes/{id}/confirm`
- **闸门**：`status != "confirmed"` 时调用 `POST /matches` 会返回 **409**
- **设计意图**：模型高置信度 **不等于** 用户确认。这是"不捏造事实"的落点
- **每条事实带**：`source_text`（原文片段）+ `source_location`（页/行/表格坐标）+ `confidence` + `created_by`

### [4] 粘贴 JD —— C 块 ⚠️

- **动作**：`POST /jobs/from-text`，提交 `title` + `content`
- **内部**：`parse_job_requirements`
  1. `detect_section` 识别章节头（含与内容同行的情况）→ 设定后续条目的必需/加分属性
  2. `split_clauses` 按分句切
  3. `classify_clause` 判必需/加分 + 类别
  4. `find_technology_mentions` 抽技能
- **写入**：`job_descriptions`（`parser_version = deterministic-job-requirements-v2`）+ `job_requirements`
- **⚠️ 内核缺口**：**只在命中技能词时才产出要求** → "3 年经验""本科以上"被直接丢弃；无城市/公司/薪资字段

### [5] 匹配 —— D 块 ⚠️

- **动作**：`POST /matches`，提交 `resume_profile_id` + `job_description_id`
- **前置**：简历必须 `confirmed`（否则 409）
- **内部**：取**已确认**的 `fact_type = skill` 事实 → 与 `job_requirements` 按 **canonical name 求交**
- **产出**：`satisfied` / `no_evidence` 两组逐项证据，每条带 JD 原文 + 简历原文 + `resume_fact_id`
- **写入**：`job_matches`，唯一约束 = 用户 + 简历 + JD + **算法版本**（`deterministic-skill-match-v1`）
  → **更新主简历不会改写历史结论**；重复调用返回同一快照
- **不做**：不输出录用概率、不输出单一匹配分（有意为之）
- **⚠️ 内核缺口**：仅精确名称匹配，无语义召回

### [6] 建议生成 —— E 块 ❌

- **动作**：`POST /optimizations`，提交同样的两个 ID
- **内部**：`create_source_backed_suggestions`
  1. 取已确认的 skill facts，找出与 JD **必需**要求匹配的那些
  2. 回溯这些技能所在的 `skills` 区段
  3. 产出 `change_type = "reorder"` 建议
- **写入**：`optimization_suggestions`（带 `resume_fact_ids` + `job_requirement_ids` + `risk` + `user_decision = pending`）
- **🔴 内核为零**：`original_text == proposed_text`，唯一动作是把技能区段**前置**。**简历字数不变、关键词不增，机筛命中率几乎不会变**

### [7] 逐条审批（硬闸门 ⛔）—— E 块 ⚠️

- **动作**：`PATCH /optimizations/{suggestion_id}`，提交 `accepted` 或 `rejected`
- **🔴 硬闸门**：存在任何 `user_decision = "pending"` 的建议时，`create_resume_version` **直接抛错**（`"Review all optimization suggestions before creating a version"`）
- **后果**：50 个岗位 × 每份约 20 条建议 = **1000 次点击，且代码强制**。这不是体验问题，是**机制性阻塞**
- **需规则变更**：高风险（涉及数字/新实体）逐条审批，低风险（措辞/排序）允许一批一次确认

### [8] 版本与导出 —— E 块 ✅

- **动作**：`POST /resume-versions`（带**幂等键**）→ `POST /resume-versions/{id}/exports/docx` → `GET /exports/{export_id}/download`
- **版本内容**：只含 `confirmed` / `user_corrected` 的**区段**事实（`fact_type != "skill"` + `SectionFactValue`），每个区段带 `source_location`；已接受的建议**只影响区段排序**
- **不可变**：版本落库后不再改写
- **导出**：中文 ATS 友好 DOCX，**24 小时**后自动清理（创建时清理 + Worker 定时清理双保险）
- **缺口**：PDF 导出未实现；无 ATS 关键词覆盖率分析

### [9] 投递与追踪 —— F 块 ❌

- **现状**：**完全不存在**（无表、无端点、无页面）
- **⚠️ 被规则禁止**：`PROJECT_RULES.md` 第 35 行、第 378 行、第 786 行三重禁止"自动投递"
- **建议形态**：按匹配度排序的岗位清单 + 一键复制定制简历 + 投递追踪表（`Application` 表）

---

## 三、旁路流程

### 旁路 1：Agent 状态机 —— G 块 ⚠️

- `POST /agent-runs` 创建任务 → Worker 领取（`FOR UPDATE SKIP LOCKED`）→ 调用**与 [6] 相同的**建议生成逻辑 → 推进到 `WAIT_USER_APPROVE_EDITS` → 持久化审批检查点 → `POST /agent-runs/{run_id}/approval` 收尾
- **已交付**：可恢复状态机、进程重启不丢任务
- **缺口**：**未接入任何模型**

### 旁路 2：公开岗位采集 —— C 块 ⚠️

- `apps/worker/job_watch.py`，由 **Windows 计划任务**每天 11:00 触发
- 仅采集**已登记、无需登录**的政府与高校官方招聘页；robots 合规、域名白名单、超时与重试上限
- 产出 `data/job_watch/*.md` + `.csv`（**本地文件，不写数据库**）
- **不在产品里**：无 API、无页面、无表 → 与主流程**完全断开**

### 旁路 3：账号删除 —— A 块 ✅

- `POST /auth/account/deletion`（需当前密码 + 确认词 `DELETE`）→ 立即冻结 + 撤销全部会话 → Worker 在 **7 天**后清除活跃业务数据与短期导出文件

---

## 四、骨架 vs 内核对照表

**这张表说明了项目的真实状态。**

| 步骤 | 骨架（工程结构） | 内核（算法质量） |
| --- | --- | --- |
| 1 注册登录 | ✅ | ✅ |
| 2 导入解析 | ✅ 三格式 + 临时文件即删 | ⚠️ 纯文本行扫描，版面信号全丢 |
| 3 事实确认 | ✅ 逐条 + 四项溯源字段 | ✅（本步本质就是人工） |
| 4 JD 解析 | ✅ 分节分句 + 202 项词典 | ⚠️ 只抽技能，经验/学历被丢弃 |
| 5 匹配 | ✅ 不可变快照 + 幂等 + 逐项证据 | ⚠️ 仅精确名称匹配 |
| 6 建议生成 | ✅ 审批流 + 证据关联 + 风险分级 | ❌ **零改写** |
| 7 逐条审批 | ✅ | ⚠️ 硬闸门，1000 次点击 |
| 8 版本导出 | ✅ 幂等 + DOCX + 24h 清理 | ✅ |
| 9 投递追踪 | ❌ | ❌ |

**结论：从注册到导出，9 步里有 8 步的"管道"是通的；但第 2、4、5、6 步的"内核"有实质缺口，而第 6 步是空的。** 项目现在的样子是：**骨架完整，内核空洞**。

---

## 五、三个硬约束（改代码前必须知道）

1. **未确认的事实不能参与匹配** —— `POST /matches` 在 `status != confirmed` 时返回 409
2. **建议必须全部处理完才能生成版本** —— 存在 `pending` 建议时 `create_resume_version` 抛错
3. **只有 `confirmed` / `user_corrected` 的事实进版本** —— `pending` 和 `rejected` 不进入

前两条是"不捏造事实"的机制保障，**第 2 条也是"1000 次点击"的机制来源**。要解决它，必须改规则（审批分层），而不是改代码。
