CREATE TABLE announcements (
    id           BIGINT PRIMARY KEY,
    title        VARCHAR(128) NOT NULL,
    content      TEXT         NOT NULL,
    status       VARCHAR(16)  NOT NULL DEFAULT 'draft',
    published_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_announcements_status ON announcements (status, published_at DESC);

CREATE TABLE announcement_reads (
    user_id         BIGINT      NOT NULL,
    announcement_id BIGINT      NOT NULL,
    read_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, announcement_id)
);

CREATE TABLE audit_logs (
    id           BIGINT PRIMARY KEY,
    operator_id  BIGINT,
    action       VARCHAR(64)  NOT NULL,
    target_type  VARCHAR(64),
    target_id    BIGINT,
    before_value JSONB,
    after_value  JSONB,
    ip           VARCHAR(64),
    request_id   VARCHAR(64),
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_operator ON audit_logs (operator_id, created_at DESC);
CREATE INDEX idx_audit_action ON audit_logs (action);

CREATE TABLE api_keys (
    id              BIGINT PRIMARY KEY,
    name            VARCHAR(64)  NOT NULL,
    provider        VARCHAR(64)  NOT NULL,
    key_cipher      TEXT,
    base_url        TEXT,
    enabled         BOOLEAN      NOT NULL DEFAULT true,
    rate_limit      INT          NOT NULL DEFAULT 60,
    health_status   VARCHAR(16)  NOT NULL DEFAULT 'unknown',
    last_checked_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE member_tiers (
    id        BIGINT PRIMARY KEY,
    name      VARCHAR(64) NOT NULL,
    level     INT         NOT NULL,
    price_cny INT         NOT NULL,
    benefits  JSONB       NOT NULL DEFAULT '{}'::jsonb,
    enabled   BOOLEAN     NOT NULL DEFAULT true
);

CREATE TABLE analytics_events (
    id         BIGINT PRIMARY KEY,
    event_name VARCHAR(64) NOT NULL,
    payload    JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_analytics_name ON analytics_events (event_name, created_at DESC);
