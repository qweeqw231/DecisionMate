# DecisionMate 后端

FastAPI 多 Agent 决策分析服务。项目整体说明见根目录 [README.md](../../README.md)。

```
decision-backend/
├── main.py                    # 入口：FastAPI 应用 + 全部路由（含 SSE 流式端点）
├── storage.py                 # SQLite 存储层（WAL 模式）
├── vector_store.py            # ChromaDB 向量检索（历史相似决策）
├── agent_core/
│   ├── ai_client.py           # DeepSeek API 统一调用
│   ├── quant_agent.py         # 量化分析 Agent（凯利公式）
│   ├── risk_agent.py          # 风险监控 Agent
│   ├── scene_agent.py         # 场景策略 Agent
│   ├── archive_agent.py       # 复盘归档 Agent
│   ├── mux.py                 # 单分身融合器
│   └── persona_mux.py         # 多分身加权融合器
├── models/schemas.py          # Pydantic 数据模型
├── static/                    # Web 前端构建产物（部署时生成，不入库）
├── requirements.txt
└── .env                       # DeepSeek 密钥配置（切勿提交）
```

启动：`uvicorn main:app --host 0.0.0.0 --port 8000`
