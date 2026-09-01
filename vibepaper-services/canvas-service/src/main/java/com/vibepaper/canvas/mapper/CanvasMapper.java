package com.vibepaper.canvas.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.vibepaper.canvas.entity.Canvas;
import org.apache.ibatis.annotations.Select;

public interface CanvasMapper extends BaseMapper<Canvas> {
    /**
     * Serializes a full graph replacement with incremental graph commands.
     * A save deletes and reinserts the complete graph, so allowing an Agent
     * command to insert a node between those two statements can otherwise
     * create a duplicate primary key.
     */
    @Select("SELECT * FROM canvases WHERE id = #{canvasId} AND deleted = false FOR UPDATE")
    Canvas selectByIdForUpdate(Long canvasId);
}
