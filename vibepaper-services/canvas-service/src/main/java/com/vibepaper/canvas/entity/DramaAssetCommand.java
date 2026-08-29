package com.vibepaper.canvas.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.vibepaper.common.mybatis.JsonbTypeHandler;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
@TableName("drama_asset_commands")
public class DramaAssetCommand {
    @TableId(type = IdType.INPUT)
    private Long id;
    private Long canvasId;
    private String idempotencyKey;
    private Long assetId;
    private String assetType;
    private Integer assetVersion;
    private Integer resultCanvasVersion;
    @TableField(typeHandler = JsonbTypeHandler.class)
    private String assetDataSnapshot;
    private OffsetDateTime createdAt;
}
