CREATE TABLE point_accounts (
    user_id       BIGINT PRIMARY KEY,
    owner_type    VARCHAR(16) NOT NULL DEFAULT 'user',
    enterprise_id BIGINT,
    balance       INT         NOT NULL DEFAULT 0 CHECK (balance >= 0),
    frozen_points INT         NOT NULL DEFAULT 0 CHECK (frozen_points >= 0 AND frozen_points <= balance),
    status        VARCHAR(16) NOT NULL DEFAULT 'active',
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_accounts_enterprise ON point_accounts (enterprise_id);

CREATE TABLE point_ledgers (
    id            BIGINT PRIMARY KEY,
    user_id       BIGINT       NOT NULL,
    ledger_type   VARCHAR(32)  NOT NULL,
    direction     VARCHAR(8)   NOT NULL CHECK (direction IN ('in', 'out')),
    points        INT          NOT NULL CHECK (points > 0),
    balance_after INT,
    task_id       BIGINT,
    order_id      BIGINT,
    reference     VARCHAR(256),
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_ledgers_user ON point_ledgers (user_id, created_at DESC);
CREATE INDEX idx_ledgers_task ON point_ledgers (task_id);
CREATE UNIQUE INDEX uq_ledgers_task_type ON point_ledgers (task_id, ledger_type) WHERE task_id IS NOT NULL;

CREATE TABLE point_reservations (
    id               BIGINT PRIMARY KEY,
    user_id          BIGINT       NOT NULL,
    account_owner_id BIGINT       NOT NULL,
    task_id          BIGINT       NOT NULL UNIQUE,
    estimated_cost   INT          NOT NULL CHECK (estimated_cost >= 1),
    status           VARCHAR(16)  NOT NULL DEFAULT 'pending',
    freeze_deadline  TIMESTAMPTZ  NOT NULL,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    settled_at       TIMESTAMPTZ
);
CREATE INDEX idx_reservations_status ON point_reservations (status, freeze_deadline);

CREATE TABLE recharge_orders (
    id              BIGINT PRIMARY KEY,
    user_id         BIGINT       NOT NULL,
    order_no        VARCHAR(64)  NOT NULL UNIQUE,
    package_id      BIGINT,
    points          INT          NOT NULL,
    amount_cny      INT          NOT NULL,
    channel         VARCHAR(32)  NOT NULL DEFAULT 'mock',
    status          VARCHAR(16)  NOT NULL DEFAULT 'pending',
    idempotency_key VARCHAR(128) NOT NULL UNIQUE,
    paid_at         TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_recharge_user ON recharge_orders (user_id, created_at DESC);

CREATE TABLE recharge_packages (
    id            BIGINT PRIMARY KEY,
    name          VARCHAR(64) NOT NULL,
    points        INT         NOT NULL,
    price_cny     INT         NOT NULL,
    validity_days INT,
    enabled       BOOLEAN     NOT NULL DEFAULT true,
    priority      INT         NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE subscription_plans (
    id         BIGINT PRIMARY KEY,
    name       VARCHAR(64) NOT NULL,
    price_cny  INT         NOT NULL,
    benefits   JSONB       NOT NULL DEFAULT '{}'::jsonb,
    enabled    BOOLEAN     NOT NULL DEFAULT true
);

CREATE TABLE user_subscriptions (
    id         BIGINT PRIMARY KEY,
    user_id    BIGINT      NOT NULL,
    plan_id    BIGINT      NOT NULL,
    status     VARCHAR(16) NOT NULL DEFAULT 'active',
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ
);
CREATE INDEX idx_subscriptions_user ON user_subscriptions (user_id, status);

CREATE TABLE outbox_events (
    id              BIGINT PRIMARY KEY,
    event_type      VARCHAR(64)  NOT NULL,
    payload         JSONB        NOT NULL,
    status          VARCHAR(16)  NOT NULL DEFAULT 'pending',
    idempotency_key VARCHAR(128),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    published_at    TIMESTAMPTZ
);
CREATE INDEX idx_outbox_status ON outbox_events (status, created_at);

INSERT INTO recharge_packages (id, name, points, price_cny, validity_days, enabled, priority) VALUES
    (1, '体验包', 100, 1, NULL, true, 1),
    (2, '入门包', 600, 5, NULL, true, 2),
    (3, '进阶包', 1300, 10, NULL, true, 3),
    (4, '专业包', 6800, 50, NULL, true, 4),
    (5, '企业包', 14000, 100, NULL, true, 5);

INSERT INTO subscription_plans (id, name, price_cny, benefits, enabled) VALUES
    (1, '免费版', 0, '{"pointsPerMonth": 100, "maxCanvases": 10}', true),
    (2, '专业版', 29, '{"pointsPerMonth": 3000, "maxCanvases": 200, "enterprise": false}', true),
    (3, '企业版', 99, '{"pointsPerMonth": 10000, "maxCanvases": -1, "enterprise": true}', true);
