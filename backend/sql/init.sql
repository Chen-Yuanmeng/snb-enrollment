-- 山那边内部报名系统（临时）初始化脚本

CREATE TABLE IF NOT EXISTS students (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    phone VARCHAR(20) NOT NULL,
    gender SMALLINT NULL,
    birth_date DATE NULL,
    school VARCHAR(100) NULL,
    grade VARCHAR(50) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    note TEXT NULL
);

CREATE INDEX IF NOT EXISTS idx_students_phone ON students(phone);
CREATE INDEX IF NOT EXISTS idx_students_name ON students(name);

CREATE TABLE IF NOT EXISTS students_history (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    grade VARCHAR(50) NULL,
    phone_suffix VARCHAR(20) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    note TEXT NULL
);

CREATE INDEX IF NOT EXISTS idx_history_name ON students_history(name);
CREATE INDEX IF NOT EXISTS idx_history_grade ON students_history(grade);

CREATE TABLE IF NOT EXISTS enrollments (
    id BIGSERIAL PRIMARY KEY,
    student_id BIGINT NOT NULL REFERENCES students(id),
    grade VARCHAR(50) NOT NULL,
    class_subjects JSONB NOT NULL,
    class_mode VARCHAR(20) NOT NULL,
    mode_details JSONB NULL,
    base_price NUMERIC(12,2) NOT NULL,
    discount_total NUMERIC(12,2) NOT NULL DEFAULT 0,
    final_price NUMERIC(12,2) NOT NULL,
    discount_info JSONB NOT NULL,
    non_price_benefits JSONB NULL,
    pricing_formula TEXT NOT NULL,
    pricing_snapshot JSONB NOT NULL,
    quote_valid_until TIMESTAMP NOT NULL,
    quote_fingerprint VARCHAR(64) NOT NULL,
    status VARCHAR(30) NOT NULL,
    valid BOOLEAN NOT NULL DEFAULT TRUE,
    operator_name VARCHAR(50) NOT NULL,
    source VARCHAR(50) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    note TEXT NULL
);

CREATE INDEX IF NOT EXISTS idx_enrollments_student ON enrollments(student_id);
CREATE INDEX IF NOT EXISTS idx_enrollments_grade_status ON enrollments(grade, status);
CREATE INDEX IF NOT EXISTS idx_enrollments_valid ON enrollments(valid);
CREATE INDEX IF NOT EXISTS idx_enrollments_quote_valid_until ON enrollments(quote_valid_until);
CREATE INDEX IF NOT EXISTS idx_enrollments_fingerprint ON enrollments(quote_fingerprint);
CREATE INDEX IF NOT EXISTS idx_enrollments_source ON enrollments(source);

CREATE TABLE IF NOT EXISTS refunds (
    id BIGSERIAL PRIMARY KEY,
    original_enrollment_id BIGINT NOT NULL REFERENCES enrollments(id),
    recalculated_enrollment_id BIGINT NULL REFERENCES enrollments(id),
    refund_class_subjects JSONB NOT NULL,
    old_price NUMERIC(12,2) NOT NULL,
    new_price NUMERIC(12,2) NOT NULL,
    refund_amount NUMERIC(12,2) NOT NULL,
    auto_rejected BOOLEAN NOT NULL DEFAULT FALSE,
    reject_reason TEXT NULL,
    review_required BOOLEAN NOT NULL DEFAULT TRUE,
    review_operator_name VARCHAR(50) NOT NULL,
    review_note TEXT NULL,
    operator_name VARCHAR(50) NOT NULL,
    source VARCHAR(50) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    note TEXT NULL
);

CREATE INDEX IF NOT EXISTS idx_refunds_original_enrollment ON refunds(original_enrollment_id);
CREATE INDEX IF NOT EXISTS idx_refunds_created_at ON refunds(created_at);

CREATE TABLE IF NOT EXISTS operation_logs (
    id BIGSERIAL PRIMARY KEY,
    operator_name VARCHAR(50) NOT NULL,
    source VARCHAR(50) NOT NULL,
    action_type VARCHAR(30) NOT NULL,
    target_type VARCHAR(30) NOT NULL,
    target_id BIGINT NULL,
    request_summary JSONB NULL,
    result_status VARCHAR(20) NOT NULL,
    message TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_logs_operator_time ON operation_logs(operator_name, created_at);
CREATE INDEX IF NOT EXISTS idx_logs_action_time ON operation_logs(action_type, created_at);
CREATE INDEX IF NOT EXISTS idx_logs_target ON operation_logs(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_logs_source_time ON operation_logs(source, created_at);

CREATE TABLE IF NOT EXISTS message_tasks (
    id BIGSERIAL PRIMARY KEY,
    message_type VARCHAR(50) NOT NULL,
    webhook_url VARCHAR(1000) NOT NULL,
    text TEXT NOT NULL,
    payload JSONB NOT NULL,
    idempotency_key VARCHAR(64) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    next_retry_at TIMESTAMP NULL,
    remote_msg_id VARCHAR(100) NULL,
    last_error TEXT NULL,
    error_chain JSONB NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    executed_at TIMESTAMP NULL
);

CREATE INDEX IF NOT EXISTS idx_message_tasks_status_next_retry
    ON message_tasks(status, next_retry_at);
CREATE INDEX IF NOT EXISTS idx_message_tasks_type ON message_tasks(message_type);
CREATE INDEX IF NOT EXISTS idx_message_tasks_webhook_url ON message_tasks(webhook_url);
CREATE INDEX IF NOT EXISTS idx_message_tasks_created_at ON message_tasks(created_at);
