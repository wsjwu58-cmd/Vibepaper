CREATE TABLE assets (
    id                    BIGINT PRIMARY KEY,
    owner_id              BIGINT       NOT NULL,
    name                  VARCHAR(128) NOT NULL,
    asset_type            VARCHAR(16)  NOT NULL,
    mime_type             VARCHAR(64),
    size_bytes            BIGINT,
    url                   TEXT,
    thumbnail_url         TEXT,
    storage_path          TEXT,
    status                VARCHAR(16)  NOT NULL DEFAULT 'ready',
    enterprise_id         BIGINT,
    certification_status  VARCHAR(16)  NOT NULL DEFAULT 'none',
    certification_reason  TEXT,
    deleted               BOOLEAN      NOT NULL DEFAULT false,
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_assets_owner ON assets (owner_id, created_at DESC);
CREATE INDEX idx_assets_enterprise ON assets (enterprise_id);
CREATE INDEX idx_assets_type ON assets (asset_type);

CREATE TABLE asset_references (
    id         BIGINT PRIMARY KEY,
    asset_id   BIGINT       NOT NULL,
    canvas_id  BIGINT,
    node_id    BIGINT,
    ref_type   VARCHAR(32)  NOT NULL DEFAULT 'canvas',
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_refs_asset ON asset_references (asset_id);
CREATE INDEX idx_refs_canvas_node ON asset_references (canvas_id, node_id);
