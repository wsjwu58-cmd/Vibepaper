CREATE TABLE users (
    id            BIGINT PRIMARY KEY,
    email         VARCHAR(255) UNIQUE,
    phone         VARCHAR(32),
    password_hash VARCHAR(100) NOT NULL,
    nickname      VARCHAR(64)  NOT NULL,
    avatar_url    TEXT,
    status        VARCHAR(16)  NOT NULL DEFAULT 'active',
    role          VARCHAR(16)  NOT NULL DEFAULT 'user',
    enterprise_id BIGINT,
    invite_code   VARCHAR(16) UNIQUE,
    invited_by    BIGINT,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ
);
CREATE INDEX idx_users_status ON users (status);
CREATE INDEX idx_users_enterprise ON users (enterprise_id);

CREATE TABLE auth_sessions (
    id                BIGINT PRIMARY KEY,
    user_id           BIGINT       NOT NULL,
    refresh_token_hash VARCHAR(128) NOT NULL,
    ip                VARCHAR(64),
    user_agent        TEXT,
    expires_at        TIMESTAMPTZ  NOT NULL,
    revoked           BOOLEAN      NOT NULL DEFAULT false,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_sessions_user ON auth_sessions (user_id);
CREATE INDEX idx_sessions_hash ON auth_sessions (refresh_token_hash);

CREATE TABLE user_preferences (
    user_id             BIGINT PRIMARY KEY,
    theme               VARCHAR(16) DEFAULT 'light',
    language            VARCHAR(16) DEFAULT 'zh',
    default_text_model  VARCHAR(64),
    default_image_model VARCHAR(64),
    default_video_model VARCHAR(64),
    default_resolution  VARCHAR(32),
    updated_at          TIMESTAMPTZ
);

CREATE TABLE user_invites (
    id            BIGINT PRIMARY KEY,
    inviter_id    BIGINT      NOT NULL,
    invitee_id    BIGINT      NOT NULL,
    reward_points INT         NOT NULL DEFAULT 100,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_invites_inviter ON user_invites (inviter_id);

CREATE TABLE daily_checkins (
    user_id       BIGINT NOT NULL,
    checkin_date  DATE   NOT NULL,
    streak        INT    NOT NULL DEFAULT 1,
    reward_points INT    NOT NULL DEFAULT 10,
    PRIMARY KEY (user_id, checkin_date)
);

CREATE TABLE daily_tasks (
    id            BIGINT PRIMARY KEY,
    task_key      VARCHAR(64) UNIQUE NOT NULL,
    title         VARCHAR(128)       NOT NULL,
    description   TEXT,
    target        INT                NOT NULL DEFAULT 1,
    reward_points INT                NOT NULL DEFAULT 10,
    enabled       BOOLEAN            NOT NULL DEFAULT true
);

CREATE TABLE user_daily_task_progress (
    user_id   BIGINT  NOT NULL,
    task_id   BIGINT  NOT NULL,
    task_date DATE    NOT NULL,
    progress  INT     NOT NULL DEFAULT 0,
    claimed   BOOLEAN NOT NULL DEFAULT false,
    PRIMARY KEY (user_id, task_id, task_date)
);

INSERT INTO daily_tasks (id, task_key, title, description, target, reward_points)
VALUES (1, 'daily_checkin', '每日签到', '完成一次每日签到', 1, 10),
       (2, 'task_generate', '完成一次生成', '成功完成任意一次 AI 生成任务', 1, 20);
