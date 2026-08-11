-- Canvas Norm 一等字段（agent-design-optimization §3.12）
ALTER TABLE canvas_nodes
    ADD COLUMN IF NOT EXISTS model_ref VARCHAR(128),
    ADD COLUMN IF NOT EXISTS prompt TEXT,
    ADD COLUMN IF NOT EXISTS output JSONB,
    ADD COLUMN IF NOT EXISTS exec_status VARCHAR(16) NOT NULL DEFAULT 'idle';

UPDATE canvas_nodes
SET model_ref = COALESCE(model_ref, params->>'model'),
    prompt = COALESCE(prompt, params->>'prompt', params->>'title'),
    exec_status = CASE
        WHEN exec_status IS NOT NULL AND exec_status <> 'idle' THEN exec_status
        WHEN stale = true THEN 'stale'
        WHEN status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled', 'expired', 'ready') THEN status
        ELSE 'idle'
    END
WHERE params IS NOT NULL AND params <> '{}';

CREATE INDEX IF NOT EXISTS idx_nodes_exec_status ON canvas_nodes (canvas_id, exec_status)
    WHERE deleted = false;
