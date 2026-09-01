package com.vibepaper.canvas.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.vibepaper.canvas.entity.CanvasGroup;
import org.apache.ibatis.annotations.Delete;

public interface CanvasGroupMapper extends BaseMapper<CanvasGroup> {

    @Delete("DELETE FROM canvas_groups WHERE canvas_id = #{canvasId}")
    int hardDeleteByCanvasId(Long canvasId);
}
