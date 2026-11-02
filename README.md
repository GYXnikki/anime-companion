# anime-companion

可私有部署的二次元角色陪伴引擎。当前完成 **P0 文字聊天后端**：流式对话、事件日志、安全兜底。

> 状态：P0 后端可用；前端、真实 LLM、语音与 Live2D 尚未接入。

## 现在能做什么

- SSE 流式文字对话
- 事件日志作为唯一真相，可按会话回放
- 危机关键词先于 LLM 生效，返回固定话术与求助指引
- 最近 20 轮上下文，从事件日志重建，不建消息投影表
- 同一会话并发生成返回 409

## 技术栈

Python 3.11 / FastAPI / Pydantic v2 / SQLite（aiosqlite）/ uv

## 快速开始

```bash
cd backend
uv sync
uv run python -m app.cli migrate
uv run uvicorn app.main:app --reload
```

```bash
curl -X POST http://127.0.0.1:8000/api/sessions
curl -N -X POST http://127.0.0.1:8000/api/sessions/<id>/messages \
  -H 'Content-Type: application/json' \
  -d '{"text":"今天有点累"}'
curl http://127.0.0.1:8000/api/sessions/<id>/events
```

## 验证

```bash
cd backend
uv run pytest
uv run ruff check .
uv run mypy app
```

## 设计文档

- [docs/design.md](docs/design.md)
- [docs/specs/0001-text-chat-mvp.md](docs/specs/0001-text-chat-mvp.md)
- [docs/adr/0001-event-log-p0.md](docs/adr/0001-event-log-p0.md)

## 边界

- 不做心理治疗或诊断，不替代专业帮助；危机输入走固定话术
- 不假装真人
- 当前使用 MockLlm，不产生真实模型回复，也未接入任何供应商

## 许可证

代码采用 [MIT License](LICENSE)。

仓库内暂无 Live2D 模型与第三方美术资产；后续资产的许可证会单独说明（计划为 CC BY-NC，与代码许可证分开）。
