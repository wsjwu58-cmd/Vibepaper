package com.vibepaper.canvas.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.vibepaper.canvas.entity.CanvasStack;
import org.apache.ibatis.annotations.Delete;

public interface CanvasStackMapper extends BaseMapper<CanvasStack> {

    @Delete("DELETE FROM canvas_stacks WHERE canvas_id = #{canvasId}")
    int hardDeleteByCanvasId(Long canvasId);
}
