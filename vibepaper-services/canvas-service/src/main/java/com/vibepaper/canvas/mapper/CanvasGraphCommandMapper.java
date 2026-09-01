package com.vibepaper.canvas.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.vibepaper.canvas.entity.CanvasGraphCommand;
import org.apache.ibatis.annotations.Select;

import java.util.Map;

public interface CanvasGraphCommandMapper extends BaseMapper<CanvasGraphCommand> {
    @Select("""
            WITH inserted AS (
                INSERT INTO canvas_graph_commands
                    (id, canvas_id, idempotency_key, operation, result_snapshot)
                VALUES (#{id}, #{canvasId}, #{idempotencyKey}, #{operation}, '{}'::jsonb)
                ON CONFLICT (canvas_id, idempotency_key) DO NOTHING
                RETURNING id, canvas_id, idempotency_key, operation, result_canvas_version,
                          result_snapshot, created_at
            )
            SELECT id, canvas_id, idempotency_key, operation, result_canvas_version,
                   result_snapshot, created_at
            FROM inserted
            UNION ALL
            SELECT id, canvas_id, idempotency_key, operation, result_canvas_version,
                   result_snapshot, created_at
            FROM canvas_graph_commands
            WHERE canvas_id = #{canvasId}
              AND idempotency_key = #{idempotencyKey}
              AND NOT EXISTS (SELECT 1 FROM inserted)
            """)
    CanvasGraphCommand claim(Map<String, Object> params);
}
