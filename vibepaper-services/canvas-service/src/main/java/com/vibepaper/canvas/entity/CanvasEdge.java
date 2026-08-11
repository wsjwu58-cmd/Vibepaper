package com.vibepaper.canvas.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
@TableName("canvas_edges")
public class CanvasEdge {
    @TableId(type = IdType.INPUT)
    private Long id;
    private Long canvasId;
    private Long sourceNodeId;
    private String sourcePort;
    private Long targetNodeId;
    private String targetPort;
    private Boolean valid;
    /** reference / input / control */
    private String dependencyType;
    @TableLogic
    private Boolean deleted;
    private OffsetDateTime createdAt;
    private OffsetDateTime updatedAt;
}
