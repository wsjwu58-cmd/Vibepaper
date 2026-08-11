package com.vibepaper.asset.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
@TableName("asset_references")
public class AssetReference {
    @TableId(type = IdType.INPUT)
    private Long id;
    private Long assetId;
    private Long canvasId;
    private Long nodeId;
    private String refType;
    private OffsetDateTime createdAt;
}
