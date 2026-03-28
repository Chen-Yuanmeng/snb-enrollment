# 企业微信集成说明

本目录使用企业微信 Webhook 方式推送消息（群机器人消息推送）。

## 目录结构

- `config.py`: 企业微信与队列配置（全部通过环境变量读取）
- `client.py`: 企业微信 Webhook 客户端
- `errors.py`: 企业微信 API 异常

## 环境变量

必须配置：

- `WECOM_REDIS_URL`: Redis 连接串，例如 `redis://127.0.0.1:6379/0`
- `WECOM_TYPE_WEBHOOK_ENV_MAPPING`: JSON 字符串，示例：
  `{\"quotation\":\"WECOM_WEBHOOK_QUOTATION\",\"payment\":\"WECOM_WEBHOOK_PAYMENT\",\"adjustment\":\"WECOM_WEBHOOK_ADJUSTMENT\",\"refund\":\"WECOM_WEBHOOK_REFUND\"}`
- `WECOM_WEBHOOK_QUOTATION` / `WECOM_WEBHOOK_PAYMENT` / `WECOM_WEBHOOK_ADJUSTMENT` / `WECOM_WEBHOOK_REFUND`:
  对应消息类型的完整 Webhook 地址

可选配置：

- `WECOM_QUEUE_KEY`: 默认 `wecom:message_tasks`
- `WECOM_RETRY_ZSET_KEY`: 默认 `wecom:message_tasks:retry`
- `WECOM_MAX_RETRIES`: 默认 `3`
- `WECOM_RETRY_BACKOFF_SECONDS`: 默认 `2`
- `WECOM_WORKER_POP_TIMEOUT_SECONDS`: 默认 `5`

## 路由映射规则

发送接口只接收 `type` 和 `text`。
系统通过以下步骤解析 webhook：

1. 从 `WECOM_TYPE_WEBHOOK_ENV_MAPPING` 中查找 `type -> webhook环境变量名`
2. 读取对应 webhook 环境变量的值并发送

注意：务必保护 webhook 地址，不可泄漏到公开仓库或日志中。

## 对外发送接口

HTTP 接口：`POST /api/v1/notifications/send`

请求体示例：

```json
{
  "operator_name": "测试",
  "source": "测试",
  "type": "quotation",
  "text": "新的报价已生成"
}
```

处理方式：

1. 主业务写入本地消息任务表
2. 推送任务 ID 到 Redis 队列
3. Worker 异步消费并调用企业微信 API
4. 失败按重试策略退避，超过上限进入 dead 状态

## Worker 启动

```bash
python -m app.workers.wecom_message_worker
```

建议生产环境使用 systemd/supervisor 托管 worker 进程。
