package com.vibepaper.canvas.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
@TableName("canvases")
public class Canvas {
    @TableId(type = IdType.INPUT)
    private Long id;
    private Long ownerId;
    private String name;
    private String description;
    private String schemaVersion;
    @Version
    private Integer version;
    private String thumbnailUrl;
    /** private / link / public */
    private String visibility;
    private String shareToken;
    @TableLogic
    private Boolean deleted;
    private OffsetDateTime createdAt;
    private OffsetDateTime updatedAt;
}
