package com.vibepaper.canvas.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.vibepaper.canvas.entity.CanvasNode;
import org.apache.ibatis.annotations.Delete;

public interface CanvasNodeMapper extends BaseMapper<CanvasNode> {

    /**
     * Full graph saves replace the complete node set.  This path must remove
     * rows physically because CanvasNode uses MyBatis-Plus logical deletion;
     * otherwise reinserting an unchanged node id violates the primary key.
     */
    @Delete("DELETE FROM canvas_nodes WHERE canvas_id = #{canvasId}")
    int hardDeleteByCanvasId(Long canvasId);
}
