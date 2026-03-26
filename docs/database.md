# 数据库设计（当前实现）

## 目标
用于报价、报名、缴费、退费、日志的完整流程，字段已按新模式统一。

## 1. students（学生主表）
- id BIGSERIAL PRIMARY KEY
- name VARCHAR(50) NOT NULL
- phone VARCHAR(20) NOT NULL
- gender SMALLINT NULL
- birth_date DATE NULL
- school VARCHAR(100) NULL
- grade VARCHAR(50) NULL
- created_at TIMESTAMP NOT NULL DEFAULT NOW()
- updated_at TIMESTAMP NOT NULL DEFAULT NOW()
- note TEXT NULL

索引：
- idx_students_phone(phone)
- idx_students_name(name)

## 2. students_history（老生表）
- id BIGSERIAL PRIMARY KEY
- name VARCHAR(50) NOT NULL
- grade VARCHAR(50) NULL
- phone_suffix VARCHAR(8) NULL
- created_at TIMESTAMP NOT NULL DEFAULT NOW()
- note TEXT NULL

索引：
- idx_history_name(name)
- idx_history_grade(grade)

## 3. enrollments（报名/报价表）
- id BIGSERIAL PRIMARY KEY
- student_id BIGINT NOT NULL REFERENCES students(id)
- grade VARCHAR(50) NOT NULL
- class_subjects JSONB NOT NULL
- class_mode VARCHAR(20) NOT NULL
- mode_details JSONB NULL
- base_price NUMERIC(12,2) NOT NULL
- discount_total NUMERIC(12,2) NOT NULL DEFAULT 0
- final_price NUMERIC(12,2) NOT NULL
- discount_info JSONB NOT NULL
- non_price_benefits JSONB NULL
- pricing_formula TEXT NOT NULL
- pricing_snapshot JSONB NOT NULL
- quote_valid_until TIMESTAMP NOT NULL
- quote_fingerprint VARCHAR(64) NOT NULL
- status VARCHAR(30) NOT NULL
- valid BOOLEAN NOT NULL DEFAULT TRUE
- operator_name VARCHAR(50) NOT NULL
- source VARCHAR(50) NOT NULL
- created_at TIMESTAMP NOT NULL DEFAULT NOW()
- updated_at TIMESTAMP NOT NULL DEFAULT NOW()
- note TEXT NULL

状态：
- quoted
- paid
- refund_requested
- refunded

索引：
- idx_enrollments_student(student_id)
- idx_enrollments_grade_status(grade, status)
- idx_enrollments_valid(valid)
- idx_enrollments_quote_valid_until(quote_valid_until)
- idx_enrollments_fingerprint(quote_fingerprint)
- idx_enrollments_source(source)

说明：
- `class_subjects` 是班型与科目合并后的多选数组。
- `source` 为来源字段，与 `operator_name` 一起用于业务追踪。
- `quote_fingerprint` 用于重复提交拦截。

## 4. refunds（退费表）
- id BIGSERIAL PRIMARY KEY
- original_enrollment_id BIGINT NOT NULL REFERENCES enrollments(id)
- recalculated_enrollment_id BIGINT NULL REFERENCES enrollments(id)
- refund_class_subjects JSONB NOT NULL
- old_price NUMERIC(12,2) NOT NULL
- new_price NUMERIC(12,2) NOT NULL
- refund_amount NUMERIC(12,2) NOT NULL
- auto_rejected BOOLEAN NOT NULL DEFAULT FALSE
- reject_reason TEXT NULL
- review_required BOOLEAN NOT NULL DEFAULT TRUE
- review_operator_name VARCHAR(50) NOT NULL
- review_note TEXT NULL
- operator_name VARCHAR(50) NOT NULL
- source VARCHAR(50) NOT NULL
- created_at TIMESTAMP NOT NULL DEFAULT NOW()
- note TEXT NULL

索引：
- idx_refunds_original_enrollment(original_enrollment_id)
- idx_refunds_created_at(created_at)

说明：
- 固定公式：`refund_amount = old_price - new_price`。
- 当差额小于等于 0 时自动拒绝。

## 5. operation_logs（操作日志表）
- id BIGSERIAL PRIMARY KEY
- operator_name VARCHAR(50) NOT NULL
- source VARCHAR(50) NOT NULL
- action_type VARCHAR(30) NOT NULL
- target_type VARCHAR(30) NOT NULL
- target_id BIGINT NULL
- request_summary JSONB NULL
- result_status VARCHAR(20) NOT NULL
- message TEXT NULL
- created_at TIMESTAMP NOT NULL DEFAULT NOW()

索引：
- idx_logs_operator_time(operator_name, created_at)
- idx_logs_action_time(action_type, created_at)
- idx_logs_target(target_type, target_id)
- idx_logs_source_time(source, created_at)

说明：
- 所有关键业务操作都记录 operator_name + source，便于后续统计与审计。
