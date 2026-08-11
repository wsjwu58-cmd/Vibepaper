package com.vibepaper.gallery.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.vibepaper.common.mybatis.JsonbTypeHandler;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
@TableName("canvas_snapshots")
public class CanvasSnapshot {
    @TableId(type = IdType.INPUT)
    private Long id;
    private Long publicationId;
    private Long canvasId;
    @com.baomidou.mybatisplus.annotation.TableField(typeHandler = JsonbTypeHandler.class)
    private String payload;
    private OffsetDateTime createdAt;
}
