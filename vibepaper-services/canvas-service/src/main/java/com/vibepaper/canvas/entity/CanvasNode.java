package com.vibepaper.canvas.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.vibepaper.common.mybatis.JsonbTypeHandler;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
@TableName("canvas_nodes")
public class CanvasNode {
    @TableId(type = IdType.INPUT)
    private Long id;
    private Long canvasId;
    /** text / image / video / audio / compose / director */
    private String nodeType;
    /** script / character / shot / keyframe / clip / audio / composite — 创作意图，可空 */
    private String creativeType;
    private Double positionX;
    private Double positionY;
    private Double width;
    private Double height;
    @TableField(typeHandler = JsonbTypeHandler.class)
    private String params;
    /** idle / queued / running / succeeded / failed / cancelled / expired / ready / stale */
    private String status;
    /** 上游 input 依赖变更后标记，Agent 可批量重跑 */
    private Boolean stale;
    /** 模型引用（Norm 一等字段） */
    private String modelRef;
    /** 创作 prompt（Norm 一等字段） */
    private String prompt;
    @TableField(typeHandler = JsonbTypeHandler.class)
    private String output;
    /** idle / ready / stale / queued / running / succeeded / failed */
    private String execStatus;
    private Long currentOutputId;
    private Long groupId;
    private Long stackId;
    @TableLogic
    private Boolean deleted;
    private OffsetDateTime createdAt;
    private OffsetDateTime updatedAt;
}
