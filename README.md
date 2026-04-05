# 山那边内部报名系统（临时）

> [!IMPORTANT]
> 
> 本项目仅作为过渡性质的临时项目使用, 请关注后续开发的正式版本

## 目录
- [`docs/database.md`](docs/database.md): 数据库设计文档
- [`docs/api.md`](docs/api.md): API 设计文档
- [`backend/`](backend/): FastAPI 后端
- [`frontend/`](frontend/): 静态前端页面
- [`docs/systemd-scripts/README.md`](docs/systemd-scripts/README.md): systemd 启动脚本示例

## 规则架构

前后端共用数据来源, 位于 [backend/rules](backend/rules) 目录下的 JSON 文件。

目前使用的规则文件包括：
- [`index.json`](backend/rules/index.json): 规则索引，定义了不同年级和学期的规则文件路径
- [`grades`](backend/rules/grades/) 目录: 包含各年级的规则文件
- [`accommodation.json`](backend/rules/accommodation.json): 住宿规则

