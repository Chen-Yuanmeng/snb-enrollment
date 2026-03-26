# API 设计草案（当前实现）

## 约定
- Base Path: /api/v1
- Content-Type: application/json
- 写接口必须传 `operator_name` 与 `source`
- 金额由后端复算，前端金额仅作展示参考

统一返回结构：
- 成功：{ code: 0, message: "ok", data: ... }
- 失败：{ code: <业务码>, message: "错误说明", data: null }

常用业务码：
- 40001 参数校验失败
- 40002 操作员未选择或无效
- 40003 重复提交
- 40005 状态流转非法
- 40006 退费金额小于等于0（自动拒绝）
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
  - status
  - sources

### GET /rules/grade/{grade}
- 说明：获取单个年级完整规则（用于退费页或按需加载）
- 参数：grade（路径参数，必须与规则中的年级名称一致）
- 返回：对应年级规则 JSON（class_modes、class_subject_groups、constraints、pricing、discounts、quote_validity、ui_hints）

## 2. 学生与老生查询
### GET /students/search
- 参数：keyword（必填）
- 返回：学生列表

### GET /students-history/search
- 参数：name（必填）, grade（可选）
- 返回：老生候选列表（id, name, grade, phone_suffix）

### GET /students-history
- 说明：老生管理列表查询（支持关键词）
- 参数（可选）：keyword, grade, limit（默认50，最大200）
- 关键词支持匹配：name / grade / phone_suffix
- 返回：老生记录列表（id, name, grade, phone_suffix, note, created_at）

### POST /students-history
- 说明：手动新增老生记录
- 入参：
  - operator_name
  - source
  - name（必填）
  - grade（可选）
  - phone_suffix（可选，最多20位）
  - note（可选）
- 返回：新增后的老生记录

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
- 参数（可选）：status, student_id, grade, valid, source, keyword
- keyword 支持：学生姓名模糊匹配；纯数字时按报名ID精确匹配
- 返回：报名列表（含 class_subjects, source, student_name, student_phone）

### GET /enrollments/{enrollment_id}
- 返回：单条详情（含 class_subjects, source, 算式、快照、优惠明细）

## 4. 缴费
### POST /enrollments/{enrollment_id}/pay
- 入参：operator_name, source, note（可选）
- 前置：状态必须是 quoted
- 处理：状态改为 paid，写日志

### POST /enrollments/pay-batch
- 入参：operator_name, source, enrollment_ids[]
- 处理：逐条校验并流转 quoted -> paid

## 5. 退费
### POST /refunds/preview
- 入参：
  - operator_name
  - source
  - original_enrollment_id
  - new_enrollment_payload（同试算入参结构）
- 处理：
  - new_enrollment_payload.source 必须与顶层 source 一致
  - 计算 old_price/new_price/refund_amount
  - refund_amount <= 0 时标记自动拒绝

### POST /refunds
- 入参与 preview 一致，增加 review_note
- 处理：
  - 原单置为 refund_requested
  - 差额 > 0 时流转为 refunded 并落退款单
  - 差额 <= 0 返回 40006（自动拒绝）

## 6. 日志
### GET /logs
- 参数（可选）：operator_name, source, action_type, target_type, page, page_size
- 返回：操作日志列表（含 operator_name 与 source）

## 7. 健康检查
### GET /health
- 返回：服务状态与数据库连通状态

## 状态流转
- quoted -> paid
- paid -> refund_requested -> refunded

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
