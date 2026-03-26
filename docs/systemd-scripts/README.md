# systemd 启动脚本

当前项目已改为由 FastAPI 在同一个端口同时提供：
- 前端静态页面（`/`）
- 后端 API（`/api/v1/*`）

因此生产启动只需要一个 systemd 服务：
- `snb-enrollment.service`

## 1. 安装服务

```bash
sudo cp /home/administrator/Desktop/snb-enrollment/docs/systemd-scripts/snb-enrollment.service /etc/systemd/system/
sudo systemctl daemon-reload
```

## 2. 设置开机自启并立即启动

```bash
sudo systemctl enable --now snb-enrollment.service
```

## 3. 查看状态与日志

```bash
sudo systemctl status snb-enrollment.service
sudo journalctl -u snb-enrollment.service -f
```

## 4. 重启与停止

```bash
sudo systemctl restart snb-enrollment.service
sudo systemctl stop snb-enrollment.service
```

## 访问地址

- 页面：`http://<服务器IP>:5555/`
- 健康检查：`http://<服务器IP>:5555/health`
- 操作员接口：`http://<服务器IP>:5555/api/v1/operators`

## 说明

- Unit 中使用用户：`administrator`。
- 如果部署用户或路径不同，请同步修改以下字段：
  - `User`
  - `Group`
  - `WorkingDirectory`
  - `ExecStart`
