# API 设计草案（当前实现）

## 约定
- Base Path: /api/v1
- Content-Type: application/json
- 写接口必须传 `operator_name` 与 `source`
- 金额由后端复算，前端金额仅作展示参考
- 时间字段语义：API 中 datetime 字段当前按 UTC naive 语义返回（多数为不带时区后缀的 ISO 字符串）
- 前端展示约定：所有页面统一按 Asia/Shanghai 进行时间展示，不使用浏览器默认时区

统一返回结构：
- 成功：{ code: 0, message: "ok", data: ... }
- 失败：{ code: <业务码>, message: "错误说明", data: null }

常用业务码：
- 40001 参数校验失败
- 40002 操作员未选择或无效
- 40003 重复提交
- 40005 状态流转非法
- 40007 来源未选择或无效
- 40401 数据不存在
- 50000 服务异常

## 1. 字典与元数据

规则唯一来源：`backend/rules/index.json` + `backend/rules/grades/*.json`。
后端在启动后直接读取规则文件用于：
- 班型与科目校验
- 上课方式校验
- 优惠互斥与老生关联校验
- 基础价、优惠、有效期计算
### GET /operators
- 说明：获取操作员列表
- 返回：[{ name }]

### GET /sources
- 说明：获取来源列表
- 返回：[{ name }]

### GET /rules/meta
- 说明：获取前端渲染元数据
- 返回：
  - version
  - timezone
  - grades
  - grade_options（含每年级 class_modes + class_subject_groups + discounts + selection_mode + max_select + ui_hints）
  - discounts 为对象数组，核心字段：name、mode（manual/auto）
  - status
  - sources

### GET /rules/grade/{grade}
- 说明：获取单个年级完整规则（用于退费页或按需加载）
- 参数：grade（路径参数，必须与规则中的年级名称一致）
- 返回：对应年级规则 JSON（class_modes、class_subject_groups、constraints、pricing、discounts、quote_validity、ui_hints）

### GET /rules/accommodation
- 说明：获取住宿报名规则（酒店、房型、时长、默认每晚价格）
- 返回：`backend/rules/accommodation.json` 的完整内容

## 2. 学生与老生查询
### GET /students/search
- 参数：keyword（必填）
- 返回：学生列表

### GET /students-history/search/renewal
- 说明：老生续报搜索
- 参数：name（必填）, grade（必填）
- 匹配规则：name 精确匹配；grade 按等价年级集合精确匹配（例如“新高一暑/五一中考/道法押题/2029届”互认）；且仅返回 `can_renew_discount=true` 的老生
- 返回：老生候选列表（id, name, grade, phone_suffix）

### GET /students-history/search/referral
- 说明：老带新搜索
- 参数：name（必填）
- 匹配规则：仅按姓名模糊匹配，不按年级过滤
- 返回：老生候选列表（id, name, grade, phone_suffix）

### GET /students-history
- 说明：老生管理列表查询（支持关键词）
- 参数（可选）：keyword, grade, page（默认1）, page_size（默认20，最大200）, limit（兼容旧参数，传入后按第一页+limit返回）
- 关键词支持匹配：name / grade / phone_suffix
- 返回：`data` 为老生记录列表（id, name, grade, phone_suffix, can_renew_discount, note, created_at），并在顶层返回分页元数据：`total`, `page`, `page_size`

### POST /students-history
- 说明：手动新增老生记录
- 入参：
  - `operator_name`（必填）
  - `source`（必填）
  - `name`（必填）
  - `grade`（可选）
  - `phone_suffix`（可选，最多20位）
  - `can_renew_discount`（必填，布尔值）
  - `note`（可选）
- 返回：新增后的老生记录

### 批量导入老生（PostgreSQL）
- 示例命令：
  - `psql "$DATABASE_URL" -c "\copy students_history(name,grade,phone_suffix,note,can_renew_discount) FROM '/path/to/students_history_import.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')"`
- CSV 文件格式（首行表头）：
  - `name,grade,phone_suffix,note,can_renew_discount`
- 布尔字段要求：
  - `can_renew_discount` 每行必须显式填写 `true` 或 `false`。

## 3. 报价与报名
### POST /quotes/calculate
- 说明：试算，不落库
- 入参：
  - operator_name
  - source
  - student_info（name, phone, ...）
  - grade
  - class_subjects（数组，多选）
  - class_mode
  - mode_details（混合时必填）
  - discounts
- 返回：
  - base_price
  - discount_total
  - final_price
  - pricing_formula
  - quote_valid_until
  - non_price_benefits
  - quote_text（后端生成的完整报价提示文本，可直接用于复制/发送）
  - pricing_snapshot

### POST /enrollments
- 说明：创建报价单（落库）
- 入参与试算一致
- 后端处理：
  - 重新计算价格
  - 生成 quote_fingerprint
  - 校验重复提交
- 返回：enrollment_id, status

### GET /enrollments
- 参数（可选）：status, student_id, grade, valid, source, keyword, page（默认1）, page_size（默认20，最大200）, limit（兼容旧参数，传入后按第一页+limit返回）, latest_only（默认 true）
- keyword 支持：学生姓名模糊匹配；纯数字时按报名ID精确匹配
- 返回：`data` 为报名列表（含 class_subjects, source, student_name, student_phone, chain_root_enrollment_id, previous_enrollment_id, adjustment_tag），并在顶层返回分页元数据：`total`, `page`, `page_size`
- 默认仅返回每条报名链最新节点（`latest_only=true`），用于“报名管理”页避免展示已被后续调整替代的旧记录

### GET /enrollments/{enrollment_id}
- 返回：单条详情（含 class_subjects, source, 算式、快照、优惠明细）

### GET /enrollments/stats
- 说明：报名统计接口
- 统计范围：仅包含 `confirmed`、`increased`、`partial_refunded`
- 统计口径：对每条报名记录按 `class_subjects` 拆分后计数（一个报名可计入多个科目）
- 线上/线下：
  - `class_mode=线下`：该报名下科目计入线下
  - `class_mode=线上`：该报名下科目计入线上
  - `class_mode=混合`：按 `mode_details.offline_subjects / online_subjects` 将每个科目分别计入线下或线上
- 返回：
  - `rows[]`：`grade`, `subject`, `offline_count`, `online_count`, `total_count`
  - `summary`：`total_rows`, `total_enrollment_subject_units`, `total_offline`, `total_online`

## 4. 缴费
### POST /enrollments/{enrollment_id}/pay
- 入参：operator_name, source, note（可选）
- 前置：状态必须是 unconfirmed（兼容历史 quoted）
- 处理：状态改为 confirmed，写日志

### POST /enrollments/pay-batch
- 入参：operator_name, source, enrollment_ids[]
- 处理：逐条校验并流转 quoted -> paid

## 5. 报名调整
### POST /refunds/preview
- 入参：
  - operator_name
  - source
  - original_enrollment_id
  - new_enrollment_payload（同试算入参结构）
- 处理：
  - new_enrollment_payload.source 必须与顶层 source 一致
  - 计算 old_price/new_price
  - 根据差额返回 branch_type：
    - increase（金额增加，需补交）
    - decrease（金额减少，可退费）
    - equal（金额不变）
  - 返回通知文案 notice_text（用于前端默认复制）

### POST /refunds
- 入参与 preview 一致，增加 review_note
- 处理：
  - 统一先将原报名置为 pending_adjustment，再生成一条新报名记录（status=unconfirmed，指向同一报名链）
  - 金额增加（increase）：生成调整任务（pending），确认后新报名=confirmed，原报名=adjusted
  - 金额减少（decrease）：生成退费任务（pending），确认后新报名=refunded，原报名=refunded
  - 金额不变（equal）：仍生成调整任务（pending），确认后新报名=confirmed，原报名=adjusted
  - 统一返回：branch_type、old_price、new_price、delta_amount、payable_amount、refundable_amount、related_ids、notice_text

### GET /refunds/adjustments/pending
- 说明：查询报名调整管理列表（名称沿用历史路径，当前返回全部调整记录）
- 参数（可选）：keyword（姓名/报名ID/退费ID）
- 返回：包含所有调整记录（未调整与已调整，含 increase/decrease/equal）

### POST /refunds/adjustments/{enrollment_id}/confirm-payment
- 说明：确认补交或金额不变调整
- 入参：operator_name, source, note（可选）

### POST /refunds/{refund_id}/confirm
- 说明：确认退费调整
- 入参：operator_name, source, note（可选）

## 6. 日志
### GET /logs
- 参数（可选）：operator_name, source, action_type, target_type, page, page_size
- 返回：操作日志列表（含 operator_name 与 source）

## 7. 健康检查
### GET /health
- 返回：服务状态与数据库连通状态

## 8. 住宿报名与确认
### POST /accommodations
- 说明：生成住宿报价单并落库
- 入参：
  - operator_name
  - source
  - related_enrollment_id（可关联任意课程报价单）
  - hotel
  - room_type
  - other_room_type_name（`room_type=其他房型` 时必填）
  - duration_days（31/27/23）
  - gender（男/女）
  - nightly_price（仅 `其他房型` 时必填，默认房型按规则自动取价）
  - note（可选）
- 返回：accommodation_id, status, quote_text, nightly_price, total_price

### GET /accommodations
- 参数（可选）：status, hotel, room_type, gender, source, keyword, page, page_size, limit
- keyword 支持：学生姓名模糊匹配；纯数字按住宿单ID/关联课程报价单ID匹配
- 返回：住宿报价列表 + 分页元数据

### POST /accommodations/{accommodation_id}/status
- 入参：operator_name, source, status(`confirmed`/`cancelled`), note（可选）
- 状态流转：
  - generated -> confirmed / cancelled
  - confirmed -> cancelled
  - cancelled -> 不允许再改

### GET /accommodations/stats
- 说明：统计住宿人数（仅统计 confirmed）
- 维度：酒店 + 房型 + 性别

### GET /accommodations/related-enrollments/search
- 说明：搜索可关联的课程报价单
- 参数（可选）：keyword, page, page_size, limit

## 状态流转
- unconfirmed -> confirmed
- confirmed -> pending_adjustment -> adjusted
- pending_adjustment/adjusted -> refunded（退费确认分支）

## 关键校验
- `operator_name` 必填且必须在配置名单中
- `source` 必填且必须在配置名单中
- `class_subjects` 必须非空，且每项必须属于当前年级允许选项
- `class_mode` 必须属于当前年级允许上课方式
- 单选年级必须严格单选，`max_select` 年级不得超选
- 折扣必须在当前年级启用，互斥优惠不能同时选
- 需要老生关联的折扣必须传 `history_student_id`
- 混合模式下 `mode_details.offline_subjects + online_subjects` 必须与 `class_subjects` 一致
- 重复提交拦截基于 quote_fingerprint
