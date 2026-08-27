-- 短剧领域资产：画布仅引用，结构化创作合同独立持久化。
CREATE TABLE drama_assets (
    id              BIGINT PRIMARY KEY,
    canvas_id       BIGINT       NOT NULL,
    asset_type      VARCHAR(32)  NOT NULL,
    asset_data      JSONB        NOT NULL DEFAULT '{}'::jsonb,
    asset_version   INT          NOT NULL DEFAULT 1,
    canvas_version  INT          NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    deleted         BOOLEAN      NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_drama_assets_canvas_idempotency
    ON drama_assets (canvas_id, idempotency_key) WHERE deleted = false;
CREATE INDEX idx_drama_assets_canvas_type ON drama_assets (canvas_id, asset_type, updated_at DESC)
    WHERE deleted = false;
