CREATE TABLE canvases (
    id             BIGINT PRIMARY KEY,
    owner_id       BIGINT       NOT NULL,
    name           VARCHAR(128) NOT NULL,
    description    TEXT,
    schema_version VARCHAR(16)  NOT NULL DEFAULT '1.0.0',
    version        INT          NOT NULL DEFAULT 1,
    thumbnail_url  TEXT,
    visibility     VARCHAR(16)  NOT NULL DEFAULT 'private',
    share_token    VARCHAR(64)  NOT NULL,
    deleted        BOOLEAN      NOT NULL DEFAULT false,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_canvases_owner ON canvases (owner_id, updated_at DESC);

CREATE TABLE canvas_nodes (
    id                BIGINT PRIMARY KEY,
    canvas_id         BIGINT       NOT NULL,
    node_type         VARCHAR(16)  NOT NULL,
    position_x        DOUBLE PRECISION NOT NULL DEFAULT 0,
    position_y        DOUBLE PRECISION NOT NULL DEFAULT 0,
    width             DOUBLE PRECISION,
    height            DOUBLE PRECISION,
    params            JSONB        NOT NULL DEFAULT '{}'::jsonb,
    status            VARCHAR(16)  NOT NULL DEFAULT 'idle',
    current_output_id BIGINT,
    group_id          BIGINT,
    stack_id          BIGINT,
    deleted           BOOLEAN      NOT NULL DEFAULT false,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_nodes_canvas ON canvas_nodes (canvas_id);
CREATE INDEX idx_nodes_group ON canvas_nodes (group_id);
CREATE INDEX idx_nodes_stack ON canvas_nodes (stack_id);

CREATE TABLE canvas_edges (
    id             BIGINT PRIMARY KEY,
    canvas_id      BIGINT      NOT NULL,
    source_node_id BIGINT      NOT NULL,
    source_port    VARCHAR(16) NOT NULL DEFAULT 'output',
    target_node_id BIGINT      NOT NULL,
    target_port    VARCHAR(16) NOT NULL DEFAULT 'input',
    valid          BOOLEAN     NOT NULL DEFAULT true,
    deleted        BOOLEAN     NOT NULL DEFAULT false,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_edges_canvas ON canvas_edges (canvas_id);
CREATE UNIQUE INDEX uq_edges_pair ON canvas_edges (canvas_id, source_node_id, target_node_id) WHERE deleted = false;

CREATE TABLE canvas_groups (
    id         BIGINT PRIMARY KEY,
    canvas_id  BIGINT       NOT NULL,
    name       VARCHAR(128) NOT NULL DEFAULT '编组',
    color      VARCHAR(16)  NOT NULL DEFAULT '#8b5cf6',
    layout     VARCHAR(16)  NOT NULL DEFAULT 'free',
    node_ids   JSONB        NOT NULL DEFAULT '[]'::jsonb,
    deleted    BOOLEAN      NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_groups_canvas ON canvas_groups (canvas_id);

CREATE TABLE canvas_stacks (
    id         BIGINT PRIMARY KEY,
    canvas_id  BIGINT       NOT NULL,
    collapsed  BOOLEAN      NOT NULL DEFAULT true,
    node_ids   JSONB        NOT NULL DEFAULT '[]'::jsonb,
    deleted    BOOLEAN      NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_stacks_canvas ON canvas_stacks (canvas_id);

CREATE TABLE canvas_revisions (
    id         BIGINT PRIMARY KEY,
    canvas_id  BIGINT      NOT NULL,
    version    INT         NOT NULL,
    payload    JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_revisions_canvas ON canvas_revisions (canvas_id, version);

CREATE TABLE canvas_shares (
    id         BIGINT PRIMARY KEY,
    canvas_id  BIGINT       NOT NULL,
    token      VARCHAR(64)  NOT NULL UNIQUE,
    visibility VARCHAR(16)  NOT NULL DEFAULT 'link',
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);
