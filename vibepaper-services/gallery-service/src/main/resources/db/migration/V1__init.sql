CREATE TABLE publications (
    id               BIGINT PRIMARY KEY,
    canvas_id        BIGINT       NOT NULL,
    owner_id         BIGINT       NOT NULL,
    title            VARCHAR(128) NOT NULL,
    status           VARCHAR(16)  NOT NULL DEFAULT 'pending',
    thumbnail_url    TEXT,
    preview_asset_url TEXT,
    rejected_reason  TEXT,
    published_at     TIMESTAMPTZ,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_publications_status ON publications (status, published_at DESC);
CREATE INDEX idx_publications_owner ON publications (owner_id);

CREATE TABLE canvas_snapshots (
    id             BIGINT PRIMARY KEY,
    publication_id BIGINT      NOT NULL,
    canvas_id      BIGINT      NOT NULL,
    payload        JSONB       NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_snapshots_pub ON canvas_snapshots (publication_id);

CREATE TABLE moderation_records (
    id             BIGINT PRIMARY KEY,
    publication_id BIGINT      NOT NULL,
    operator_id    BIGINT      NOT NULL,
    action         VARCHAR(16) NOT NULL,
    reason         TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_moderation_pub ON moderation_records (publication_id);
