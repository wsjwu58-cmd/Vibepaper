package com.vibepaper.canvas.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.vibepaper.common.mybatis.JsonbTypeHandler;
import lombok.Data;

import java.time.OffsetDateTime;

/** Persisted result for a retriable Agent graph command. */
@Data
@TableName("canvas_graph_commands")
public class CanvasGraphCommand {
    @TableId(type = IdType.INPUT)
    private Long id;
    private Long canvasId;
    private String idempotencyKey;
    private String operation;
    private Integer resultCanvasVersion;
    @TableField(typeHandler = JsonbTypeHandler.class)
    private String resultSnapshot;
    private OffsetDateTime createdAt;
}
