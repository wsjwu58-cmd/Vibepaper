CREATE TABLE IF NOT EXISTS canvas_graph_commands (
    id BIGINT PRIMARY KEY,
    canvas_id BIGINT NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    operation VARCHAR(64) NOT NULL,
    result_canvas_version INT,
    result_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_canvas_graph_commands_canvas_key
    ON canvas_graph_commands (canvas_id, idempotency_key);
