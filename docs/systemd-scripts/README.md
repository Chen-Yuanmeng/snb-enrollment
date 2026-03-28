# systemd 启动脚本

当前项目生产运行包含两个进程：
- 主程序（FastAPI + 前端静态页面）：`snb-enrollment.service`
- 企业微信异步消费 Worker：`snb-enrollment-wecom-worker.service`

为便于统一启停，提供一个聚合 target：`snb-enrollment.target`。

## 0. 准备环境变量文件（Worker 必需）

`snb-enrollment-wecom-worker.service` 会读取以下文件（不存在时自动忽略）：

- `/etc/snb-enrollment/common.env`
- `/etc/snb-enrollment/wecom-worker.env`

建议创建命令：

```bash
sudo mkdir -p /etc/snb-enrollment
sudo tee /etc/snb-enrollment/wecom-worker.env >/dev/null <<'EOF'
WECOM_CORP_ID=wwxxxxxxxxxxxxxxxx
WECOM_AGENT_ID=1000002
WECOM_AGENT_SECRET=xxxxxxxxxxxxxxxx
WECOM_REDIS_URL=redis://127.0.0.1:6379/0

# 可选
WECOM_API_BASE_URL=https://qyapi.weixin.qq.com
WECOM_MESSAGE_TYPE_CHAT_MAPPING={"quote_generated":"chatid_xxx"}
WECOM_ROUTE_STORE_PATH=/home/administrator/Desktop/snb-enrollment/backend/app/integrations/wecom/group_routes.json
WECOM_MAX_RETRIES=3
WECOM_WORKER_POP_TIMEOUT_SECONDS=5
EOF

sudo chmod 600 /etc/snb-enrollment/wecom-worker.env
sudo chown root:root /etc/snb-enrollment/wecom-worker.env
```

如果主程序和 Worker 需要共享变量（如 `DATABASE_URL`），可放到 `/etc/snb-enrollment/common.env`。

## 1. 安装服务与 target

```bash
sudo cp /home/administrator/Desktop/snb-enrollment/docs/systemd-scripts/snb-enrollment.service /etc/systemd/system/
sudo cp /home/administrator/Desktop/snb-enrollment/docs/systemd-scripts/snb-enrollment-wecom-worker.service /etc/systemd/system/
sudo cp /home/administrator/Desktop/snb-enrollment/docs/systemd-scripts/snb-enrollment.target /etc/systemd/system/
sudo systemctl daemon-reload
```

## 2. 设置开机自启并立即启动（推荐）

```bash
sudo systemctl enable --now snb-enrollment.target
```

如果修改了 env 文件，记得重载并重启：

```bash
sudo systemctl daemon-reload
sudo systemctl restart snb-enrollment-wecom-worker.service
```

## 3. 查看状态与日志

```bash
sudo systemctl status snb-enrollment.target
sudo systemctl status snb-enrollment.service
sudo systemctl status snb-enrollment-wecom-worker.service

sudo journalctl -u snb-enrollment.service -f
sudo journalctl -u snb-enrollment-wecom-worker.service -f
```

## 4. 重启与停止

```bash
sudo systemctl restart snb-enrollment.target
sudo systemctl stop snb-enrollment.target
```

如果只想单独重启某一个进程：

```bash
sudo systemctl restart snb-enrollment.service
sudo systemctl restart snb-enrollment-wecom-worker.service
```

## 访问地址

- 页面：`http://<服务器IP>:5555/`
- 健康检查：`http://<服务器IP>:5555/health`
- 操作员接口：`http://<服务器IP>:5555/api/v1/operators`

## 说明

- Unit 中默认使用用户：`administrator`。
- 如果部署用户或路径不同，请同步修改以下字段：
  - `User`
  - `Group`
  - `WorkingDirectory`
  - `ExecStart`
  - `EnvironmentFile`
