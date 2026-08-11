package com.vibepaper.canvas.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.vibepaper.common.mybatis.LongListTypeHandler;
import lombok.Data;

import java.time.OffsetDateTime;
import java.util.List;

@Data
@TableName("canvas_groups")
public class CanvasGroup {
    @TableId(type = IdType.INPUT)
    private Long id;
    private Long canvasId;
    private String name;
    private String color;
    private String layout;
    @TableField(typeHandler = LongListTypeHandler.class)
    private List<Long> nodeIds;
    @TableLogic
    private Boolean deleted;
    private OffsetDateTime createdAt;
    private OffsetDateTime updatedAt;
}
