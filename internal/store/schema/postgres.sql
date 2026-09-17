-- PostgreSQL 建表。自增主键用 BIGSERIAL，浮点用 DOUBLE PRECISION，时间用 TIMESTAMP（无时区，存 UTC）。
-- timestamp 既是列名又是类型名，所有出现处一律加双引号，免得解析器把它当类型。
-- 现有生产库的自增主键是 SERIAL（int4），IF NOT EXISTS 不会把它改成 int8；int4 读进 int64 没问题。

CREATE TABLE IF NOT EXISTS balance_history (
    id BIGSERIAL NOT NULL,
    project_id VARCHAR(200) NOT NULL,
    project_name VARCHAR(200) NOT NULL,
    provider VARCHAR(50) NOT NULL,
    balance DOUBLE PRECISION NOT NULL,
    threshold DOUBLE PRECISION,
    balance_type VARCHAR(20),
    need_alarm BOOLEAN,
    "timestamp" TIMESTAMP,
    PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_balance_history_project_id ON balance_history (project_id);
CREATE INDEX IF NOT EXISTS ix_balance_history_provider ON balance_history (provider);
CREATE INDEX IF NOT EXISTS ix_balance_history_timestamp ON balance_history ("timestamp");
CREATE INDEX IF NOT EXISTS idx_project_time ON balance_history (project_id, "timestamp");
CREATE INDEX IF NOT EXISTS idx_provider_time ON balance_history (provider, "timestamp");

CREATE TABLE IF NOT EXISTS alert_history (
    id BIGSERIAL NOT NULL,
    project_id VARCHAR(200) NOT NULL,
    project_name VARCHAR(200) NOT NULL,
    alert_type VARCHAR(50) NOT NULL,
    status VARCHAR(20),
    message TEXT,
    balance_value DOUBLE PRECISION,
    threshold_value DOUBLE PRECISION,
    "timestamp" TIMESTAMP,
    PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_alert_history_project_id ON alert_history (project_id);
CREATE INDEX IF NOT EXISTS ix_alert_history_alert_type ON alert_history (alert_type);
CREATE INDEX IF NOT EXISTS ix_alert_history_timestamp ON alert_history ("timestamp");
CREATE INDEX IF NOT EXISTS idx_project_type_time ON alert_history (project_id, alert_type, "timestamp");

CREATE TABLE IF NOT EXISTS project_config (
    id BIGSERIAL NOT NULL,
    name VARCHAR(200) NOT NULL,
    owner_project VARCHAR(200),
    provider VARCHAR(50) NOT NULL,
    api_key TEXT NOT NULL,
    threshold DOUBLE PRECISION,
    type VARCHAR(20),
    enabled BOOLEAN,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE (name)
);

CREATE INDEX IF NOT EXISTS ix_project_config_owner_project ON project_config (owner_project);

CREATE TABLE IF NOT EXISTS subscription_config (
    id BIGSERIAL NOT NULL,
    name VARCHAR(200) NOT NULL,
    owner_project VARCHAR(200),
    cycle_type VARCHAR(20),
    renewal_day INTEGER,
    alert_days_before INTEGER,
    amount DOUBLE PRECISION,
    enabled BOOLEAN,
    last_renewed_date VARCHAR(20),
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE (name)
);

CREATE INDEX IF NOT EXISTS ix_subscription_config_owner_project ON subscription_config (owner_project);

CREATE TABLE IF NOT EXISTS email_config (
    id BIGSERIAL NOT NULL,
    name VARCHAR(200) NOT NULL,
    host VARCHAR(200) NOT NULL,
    port INTEGER,
    username VARCHAR(200) NOT NULL,
    password TEXT NOT NULL,
    use_ssl BOOLEAN,
    enabled BOOLEAN,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE (name)
);

CREATE TABLE IF NOT EXISTS email_alert_history (
    id BIGSERIAL NOT NULL,
    mailbox VARCHAR(200) NOT NULL,
    sender VARCHAR(200) NOT NULL,
    subject VARCHAR(500) NOT NULL,
    date VARCHAR(100) NOT NULL,
    service_name VARCHAR(200),
    amount DOUBLE PRECISION,
    matched_keywords TEXT,
    alert_sent BOOLEAN,
    "timestamp" TIMESTAMP,
    PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_email_alert_history_mailbox ON email_alert_history (mailbox);
CREATE INDEX IF NOT EXISTS ix_email_alert_history_timestamp ON email_alert_history ("timestamp");
CREATE INDEX IF NOT EXISTS idx_email_mailbox_time ON email_alert_history (mailbox, "timestamp");
