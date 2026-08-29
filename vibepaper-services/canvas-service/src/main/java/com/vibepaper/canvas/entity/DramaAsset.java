package com.vibepaper.canvas.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableLogic;
import com.baomidou.mybatisplus.annotation.TableName;
import com.vibepaper.common.mybatis.JsonbTypeHandler;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
@TableName("drama_assets")
public class DramaAsset {
    @TableId(type = IdType.INPUT)
    private Long id;
    private Long canvasId;
    private String assetType;
    @TableField(typeHandler = JsonbTypeHandler.class)
    private String assetData;
    private Integer assetVersion;
    private Integer canvasVersion;
    private String idempotencyKey;
    @TableLogic
    private Boolean deleted;
    private OffsetDateTime createdAt;
    private OffsetDateTime updatedAt;
}
