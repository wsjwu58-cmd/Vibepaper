CREATE TABLE enterprises (
    id                     BIGINT PRIMARY KEY,
    name                   VARCHAR(128) NOT NULL,
    owner_id               BIGINT       NOT NULL,
    enterprise_code        VARCHAR(32)  NOT NULL UNIQUE,
    total_points           INT          NOT NULL DEFAULT 0,
    allocatable_points     INT          NOT NULL DEFAULT 0,
    shared_pool_enabled    BOOLEAN      NOT NULL DEFAULT false,
    admin_can_view_content BOOLEAN      NOT NULL DEFAULT false,
    status                 VARCHAR(16)  NOT NULL DEFAULT 'active',
    created_at             TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE enterprise_members (
    enterprise_id BIGINT       NOT NULL,
    user_id       BIGINT       NOT NULL,
    role          VARCHAR(16)  NOT NULL DEFAULT 'member',
    joined_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (enterprise_id, user_id)
);
CREATE INDEX idx_members_user ON enterprise_members (user_id);

CREATE TABLE enterprise_invitations (
    id            BIGINT PRIMARY KEY,
    enterprise_id BIGINT       NOT NULL,
    token         VARCHAR(64)  NOT NULL UNIQUE,
    inviter_id    BIGINT       NOT NULL,
    status        VARCHAR(16)  NOT NULL DEFAULT 'pending',
    expires_at    TIMESTAMPTZ  NOT NULL,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_invitations_ent ON enterprise_invitations (enterprise_id, status);

CREATE TABLE allocation_records (
    id            BIGINT PRIMARY KEY,
    enterprise_id BIGINT       NOT NULL,
    operator_id   BIGINT       NOT NULL,
    member_id     BIGINT       NOT NULL,
    alloc_type    VARCHAR(16)  NOT NULL,
    points        INT          NOT NULL,
    balance_after INT,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_allocation_ent ON allocation_records (enterprise_id, created_at DESC);
CREATE INDEX idx_allocation_member ON allocation_records (member_id);
