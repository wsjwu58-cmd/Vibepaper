package com.vibepaper.canvas.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.vibepaper.common.mybatis.LongListTypeHandler;
import lombok.Data;

import java.time.OffsetDateTime;
import java.util.List;

@Data
@TableName("canvas_stacks")
public class CanvasStack {
    @TableId(type = IdType.INPUT)
    private Long id;
    private Long canvasId;
    private Boolean collapsed;
    @TableField(typeHandler = LongListTypeHandler.class)
    private List<Long> nodeIds;
    @TableLogic
    private Boolean deleted;
    private OffsetDateTime createdAt;
    private OffsetDateTime updatedAt;
}
