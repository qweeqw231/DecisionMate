# DecisionMate · 个人决策支持系统

基于多 Agent 的个人决策支持系统：用户描述决策场景，系统通过元认知调度器路由到「快回路（直觉建议）」或「慢回路（多 Agent 会商）」，输出包含凯利公式仓位、风险评估、场景策略时间线的结构化决策报告，并支持决策反馈驱动的能力画像演化与复盘归档。

## 功能特性

- **元认知路由**：简单/紧急场景走快回路秒回直觉建议；复杂场景自动进入慢回路多 Agent 会商
- **多分身会商**：激进 / 中性 / 保守分身并行量化分析，支持创建自定义分身（上限 3 个）并按权重加权融合；分身会商表可逐行展开，查看每个分身的完整分析意见（胜率/赔率/凯利值与推理过程）
- **分身管理**：自定义分身创建后可随时编辑名称、风险偏好与核心原则；预置分身支持一键重置
- **场景策略**：识别单次/多阶段/学期级复合体等场景，输出带日期范围的分阶段策略时间线
- **复盘归档**：对决策结果提交有效/不准确/自定义反馈，系统生成偏差分析、能力因子更新与新因子提议，沉淀可复用模式
- **流式输出**：SSE 推送各分析阶段进度，支持随时中止
- **地址可配置**：无云服务器场景下后端 IP 可变，前端支持运行时配置地址或由后端同源托管

## 架构

```
web-frontend/          # Vue 3 + TypeScript + Pinia + Element Plus（当前主力前端）
decision-backend/      # FastAPI + SQLite(WAL) + ChromaDB + DeepSeek API
DecisionMate-frontend/ # 鸿蒙 ArkTS 前端（已停更，仅作历史参考）
个人决策支持系统文档/    # Phase 1~4 需求文档与验收记录
```

### 后端核心流程（慢回路）

多分身（激进/中性/保守/自定义）并行量化分析 → 风险评估 → 场景策略分析 → Mux 加权融合，辅以历史相似决策向量检索与用户能力画像注入。所有 LLM 调用共享 DeepSeek API，Agent 差异由 System Prompt 体现。

### 后端 API

- `POST /api/conversations/{id}/messages` — 同步发送决策消息（返回完整报告）
- `POST /api/conversations/{id}/messages/stream` — SSE 流式版，推送阶段事件（分身量化/风险/场景/融合）
- 对话 CRUD / 置顶 / 重命名 / 清空、消息列表、反馈与归档
- 分身 CRUD / 权重调整 / 预置重置（自定义上限 3 个）
- `GET /api/user-profile`、`POST /api/user-profile/add-factor` — 能力画像
- `GET /api/health` — 健康检查

## 快速开始

### 后端

```powershell
cd decision-backend/decision-backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# 在 .env 中配置 DeepSeek API Key 等（见 .env.example 或 README）
.\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
```

`.env` 需要的键：`DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`LLM_MODEL`、`EMBEDDING_BASE_URL`、`EMBEDDING_API_KEY`、`EMBEDDING_MODEL` 等。

### 前端（开发模式）

```powershell
cd web-frontend
npm install
npm run dev    # http://localhost:5173，/api 自动代理到 127.0.0.1:8000
```

### 部署（无云服务器，后端 IP 可能漂移）

- **方式一（推荐）：同源托管**。`npm run build` 后把 `dist/` 内容复制到后端 `static/` 目录，重启后端。局域网设备访问 `http://<后端IP>:8000` 即可，后端换 IP 前端零配置，且同源零 CORS。
- **方式二：独立部署**。构建产物部署到任意静态服务器，在前端「设置」页填写后端地址（如 `http://192.168.1.100:8000`），地址持久化在浏览器 localStorage，可随时修改。

## 技术栈

| 层 | 技术 |
|---|---|
| Web 前端 | Vue 3、TypeScript、Pinia、Element Plus、Vite（SSE 用 fetch + ReadableStream） |
| 后端 | FastAPI、SQLite（WAL）、ChromaDB（向量检索）、OpenAI SDK（DeepSeek 兼容接口） |
| 遗留 | 鸿蒙 ArkTS（DecisionMate-frontend，已停更） |

## 说明

- 系统无鉴权，仅限本机/局域网使用；`.env` 含密钥，切勿提交
- 决策记录与消息在落库时直接绑定，反馈可精确触发复盘归档
- SQLite 并发已启用 WAL
