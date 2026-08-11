package com.vibepaper.canvas.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.vibepaper.common.mybatis.JsonbTypeHandler;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
@TableName("canvas_revisions")
public class CanvasRevision {
    @TableId(type = IdType.INPUT)
    private Long id;
    private Long canvasId;
    private Integer version;
    @com.baomidou.mybatisplus.annotation.TableField(typeHandler = JsonbTypeHandler.class)
    private String payload;
    private OffsetDateTime createdAt;
}
