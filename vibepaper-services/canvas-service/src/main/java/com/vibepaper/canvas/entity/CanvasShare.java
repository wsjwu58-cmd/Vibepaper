package com.vibepaper.canvas.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
@TableName("canvas_shares")
public class CanvasShare {
    @TableId(type = IdType.INPUT)
    private Long id;
    private Long canvasId;
    private String token;
    private String visibility;
    private OffsetDateTime createdAt;
    private OffsetDateTime updatedAt;
}
