-- Canvas Norm：创作领域语义（agent-design-optimization §5.5a / §3.12）
ALTER TABLE canvas_nodes
    ADD COLUMN IF NOT EXISTS creative_type VARCHAR(32),
    ADD COLUMN IF NOT EXISTS stale BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE canvas_edges
    ADD COLUMN IF NOT EXISTS dependency_type VARCHAR(16) NOT NULL DEFAULT 'reference';

CREATE INDEX IF NOT EXISTS idx_nodes_creative_type ON canvas_nodes (canvas_id, creative_type)
    WHERE deleted = false;
CREATE INDEX IF NOT EXISTS idx_nodes_stale ON canvas_nodes (canvas_id, stale)
    WHERE deleted = false AND stale = true;
CREATE INDEX IF NOT EXISTS idx_edges_dependency ON canvas_edges (canvas_id, dependency_type)
    WHERE deleted = false;
