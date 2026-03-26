# 山那边内部报名系统（测试版）

## 目录
- docs/database.md: 数据库设计文档
- docs/api.md: API 设计文档
- info-new.md: 业务规则说明（人工可读）
- backend/: FastAPI 后端
- frontend/: 静态前端页面

## 当前模型（已切换）
- 班型与科目采用单一字段 `class_subjects`（数组，多选）
- 报价与缴费操作采用 `operator_name + source` 双字段
- 日志表同步记录 `operator_name` 和 `source`

## 规则架构（已切换）
- 规则唯一来源：`backend/rules/index.json` + `backend/rules/grades/*.json`
- 后端直接读取规则文件进行：
	- 报名校验（年级、班型科目、上课方式、优惠约束）
	- 价格计算（基础价、优惠金额、报价有效期）
- 前端通过 API 获取规则后渲染页面：
	- 报名页：`GET /api/v1/rules/meta`
	- 退费页：`GET /api/v1/rules/meta`（可扩展按需调用 `GET /api/v1/rules/grade/{grade}`）

规则文件参考：
- `backend/rules/index.json`
- `backend/rules/grades/s1_summer.json`
- `backend/rules/grades/s2_summer.json`
- `backend/rules/grades/s3_summer.json`

## 后端启动
1. 进入目录：`cd backend`
2. 安装依赖：`pip install -r requirements.txt`
3. 配置数据库连接：在 `backend/.env` 写入 `DATABASE_URL`
4. 启动服务：`uvicorn app.main:app --reload --port 3030`

说明：
- 测试阶段默认开启启动重建库（`RESET_DB_ON_STARTUP=1`），每次启动会删除并重建表结构。
- 如需保留数据，可设置 `RESET_DB_ON_STARTUP=0`。

## 前端启动
可直接通过静态服务打开 `frontend/index.html`。

示例：
- `python -m http.server 8080`（在项目根目录）
- 浏览器访问 `http://127.0.0.1:8080/frontend/`

## 运行测试
进入 `backend` 后执行：`pytest -q`

## 备注
- 当前文档与代码已按破坏性升级口径同步，不再兼容旧的 `class_type + subjects` 入参结构。
- `info-new.md` 仅作为业务说明，代码执行以 `backend/rules/*.json` 为准。
