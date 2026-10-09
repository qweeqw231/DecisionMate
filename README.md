# DecisionMate · 个人决策支持系统

基于多 Agent 的个人决策支持系统：用户描述决策场景，系统通过元认知调度器路由到「快回路（直觉建议）」或「慢回路（多 Agent 会商）」，输出包含凯利公式仓位、风险评估、场景策略时间线的结构化决策报告，并支持决策反馈驱动的能力画像演化与复盘归档。

## 功能特性

> 标注「Web」的条目**只在 Vue 前端实现**；鸿蒙端没有对应功能，详见下方「前端维护状态」。

- **元认知路由**：简单/紧急场景走快回路秒回直觉建议；复杂场景自动进入慢回路多 Agent 会商
- **多分身会商**：激进 / 中性 / 保守分身并行量化分析，支持创建自定义分身（上限 3 个）并按权重加权融合；分身会商表可逐行展开，查看每个分身的完整分析意见（胜率/赔率/凯利值与推理过程）
- **分身管理**：自定义分身创建后可随时编辑名称、风险偏好与核心原则；预置分身支持一键重置
- **场景策略**：识别单次/多阶段/学期级复合体等场景，输出带日期范围的分阶段策略时间线
- **复盘归档**：对决策结果提交有效/不准确/自定义反馈，系统生成偏差分析、能力因子更新与新因子提议，沉淀可复用模式
- **能力因子写入守卫**：所有因子写入都会校验（只允许更新已有因子、必须是数值、钳制在 0~1、单次幅度 ≤±0.05），并在复盘报告中列出被钳制/拒绝的项，避免「模型提议了但没生效」无从解释
- **关系边界保护（Web）**：识别到决策对象是「具体的、平等的他人」时主动关机——不做量化、不给建议，并默认**不写入任何记录**；硬规则词表、关机文案与是否落库均可在设置页配置
- **执行中校准 / L1（Web）**：决策执行过程中可记录阶段性进展，系统重新估算胜率与赔率、由确定性凯利引擎重算 f\*，并给出「继续执行 / 观望 / 及时止损」的判定；初始预判与逐次校准以轨迹表格对比展示
- **历史参考（Web）**：慢回路会把检索到的相似历史决策连同相似度、参数一并展示，而不是只悄悄注入 Prompt
- **系统自省 / L3（Web）**：汇总系统运行以来的决策数据（决策级准确率、建议档位分布、月度趋势、按场景拆分、冲突与降级率、当前 Mux 参数与关系边界配置），供你判断是否存在系统性偏差
- **流式输出**：SSE 推送各分析阶段进度，支持随时中止
- **地址可配置**：无云服务器场景下后端 IP 可变，前端支持运行时配置地址或由后端同源托管

## 架构

```
web-frontend/          # Vue 3 + TypeScript + Pinia + Element Plus（唯一在维护的前端）
decision-backend/      # FastAPI + SQLite(WAL) + ChromaDB + DeepSeek API
launcher/              # 桌面快捷方式启动器（点击即用，关闭页面自动停止）
test-harness/          # 附属测试程序：场景生成 / 批量跑测 / 人工复核台
DecisionMate-frontend/ # 鸿蒙 ArkTS 前端（已冻结，仅作历史参考，不再跟进后端演进）
个人决策支持系统文档/    # Phase 1~4 需求文档与验收记录
```

### 前端维护状态（请勿误读）

- **`web-frontend/` 是唯一在维护的前端。**
- **`DecisionMate-frontend/`（鸿蒙 ArkTS）已冻结**：不再新增功能、不再跟随后端演进，保留在仓库里只为历史参考。
- 因此，README 里标注「Web」的功能，以及历次修复，**鸿蒙端一律没有对应实现**。不要把它理解为「前端问题已全部解决」——只解决了 Web 端。

鸿蒙端当前确切的落后项（可逐条核对代码）：

| 项目 | 鸿蒙端现状 |
|---|---|
| 关系边界关机 | 没有界面；且它调用的 `POST /api/decision` 现在可能返回 `loop_type="boundary"` 的关机报告，而 `DecisionModels.ets` 的 `DecisionReport` 没有 `loop_type` 字段，会把关机报告当作普通报告解析 |
| 冲突标记文案 | `ResultPage.ets` 对 `conflict_detected` 固定显示「分身意见分歧」；该字段如今也覆盖「生存优先硬约束」冲突，会标注错误 |
| 新因子提议 | `InputPage.ets` 的 `acceptNewFactor` 先弹「已添加」再异步调用接口，且把失败仅 `console.error`；后端返回 400 时用户仍被告知成功 |
| 执行中校准（L1） | 没有进展录入入口，也没有轨迹展示 |
| 风险校验降级 / 边界校验降级 | 模型里没有对应字段，也没有提示 |
| 历史参考 | 没有展示 |
| 系统自省看板、关系边界配置 | 没有入口 |

### 后端核心流程（慢回路）

关系边界前置判定 → 多分身（激进/中性/保守/自定义）并行量化分析 → 风险评估 → 场景策略分析 → Mux 加权融合（含生存优先硬约束），辅以历史相似决策向量检索与用户能力画像注入。所有 LLM 调用共享 DeepSeek API，Agent 差异由 System Prompt 体现。

### 后端 API

- `POST /api/conversations/{id}/messages` — 同步发送决策消息（返回完整报告）
- `POST /api/conversations/{id}/messages/stream` — SSE 流式版，推送阶段事件（关系边界/分身量化/风险/场景/融合）
- 对话 CRUD / 置顶 / 重命名 / 清空、消息列表、反馈与归档
- 分身 CRUD / 权重调整 / 预置重置（自定义上限 3 个）
- `GET /api/user-profile`、`POST /api/user-profile/add-factor` — 能力画像（后者接收 JSON 请求体）
- `GET /api/system-audit` — L3 系统自省汇总（只读）
- `GET|POST /api/boundary-config`、`POST /api/boundary-config/reset` — 关系边界配置
- `GET|POST /api/conversations/{id}/messages/{msg_id}/execution-updates` — L1 执行中校准（记录进展 / 读取「初始预判 → 逐次校准」轨迹）
- `GET /api/health` — 健康检查

### 回归测试

```powershell
cd decision-backend/decision-backend
.\.venv\Scripts\python.exe run_tests.py        # 全部用例（标准库 unittest，无需 pytest）
```

测试数据全部落在系统临时目录，不会触碰 `decision.db` 与 `chroma_db`。

### 运维脚本

```powershell
.\.venv\Scripts\python.exe tools\repair_profile.py            # 巡检/还原被写坏的能力画像（默认 dry-run）
.\.venv\Scripts\python.exe tools\clean_orphan_vectors.py      # 巡检/清理孤儿向量（默认 dry-run）
```

## 快速开始

### 桌面快捷方式（推荐日常使用）

运行 `launcher/install_shortcuts.ps1` 在桌面创建两个快捷方式（点击即用，用完即停，不常驻内存）：

- **DecisionMate（主程序）**：启动后端并由其同源托管前端静态文件（单进程，无需再单独启动前端 dev server），自动打开浏览器；**关闭浏览器页面约 10 秒后自动停止服务**。控制台窗口会打印局域网地址（手机/平板可用）；关闭控制台窗口或 Ctrl+C 可立即停止。
- **DecisionMate 测试台**：启动测试复核台（8020），同样关闭页面自动停止。

自动停止基于页面心跳（主程序端口 8011 / 测试台 8021，脚本已内嵌在页面中）；不用快捷方式而手动启动服务时，心跳脚本无副作用。

### 后端（手动启动，开发/调试用）

```powershell
cd decision-backend/decision-backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# 在 .env 中配置密钥（该文件已被 gitignore，仓库未提供 .env.example）
.\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
```

`.env` 实际只用到两个键：`DEEPSEEK_API_KEY`（对话模型，DeepSeek）与 `SILICONFLOW_API_KEY`（向量嵌入，`BAAI/bge-large-zh-v1.5`，走 SiliconFlow）。模型名与 base_url 目前硬编码在 `agent_core/ai_client.py` 与 `vector_store.py`，并不通过环境变量配置。

### 前端（开发模式）

```powershell
cd web-frontend
npm install
npm run dev    # http://localhost:5173，/api 自动代理到 127.0.0.1:8000
```

### 部署（无云服务器，后端 IP 可能漂移）

- **方式一（推荐）：同源托管**。`npm run build` 后把 `dist/` 内容复制到后端 `static/` 目录，重启后端。局域网设备访问 `http://<后端IP>:8000` 即可，后端换 IP 前端零配置，且同源零 CORS。
- **方式二：独立部署**。构建产物部署到任意静态服务器，在前端「设置」页填写后端地址（如 `http://192.168.1.100:8000`），地址持久化在浏览器 localStorage，可随时修改。

### 附属测试程序（test-harness）

```powershell
cd test-harness
python scenario_generator.py   # 批量生成决策测试场景（按类别，可用 --limit 试跑）
python batch_runner.py         # 批量喂给隔离后端实例跑测（自动复制数据库副本，不触碰真实数据）
python review_app.py           # 复核台（8020），或使用桌面「DecisionMate 测试台」快捷方式
```

## 技术栈

| 层 | 技术 |
|---|---|
| Web 前端 | Vue 3、TypeScript、Pinia、Element Plus、Vite（SSE 用 fetch + ReadableStream）—— 唯一在维护的前端 |
| 后端 | FastAPI、SQLite（WAL）、ChromaDB（向量检索）、OpenAI SDK（DeepSeek 兼容接口） |
| 遗留 | 鸿蒙 ArkTS（DecisionMate-frontend，已冻结；不随 Web 端修复同步） |

## 说明

- 系统无鉴权，仅限本机/局域网使用；`.env` 含密钥，切勿提交
- 决策记录与消息在落库时直接绑定，反馈可精确触发复盘归档
- SQLite 并发已启用 WAL
- **关系边界命中时默认不落库**（消息、决策记录、向量库均不写入），这是架构要求的行为，不是 bug
- 前端问题只保证了 Web 端；鸿蒙端为冻结代码，已知落后项见「前端维护状态」
