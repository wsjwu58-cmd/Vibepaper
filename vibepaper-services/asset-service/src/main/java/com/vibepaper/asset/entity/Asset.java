package com.vibepaper.asset.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
@TableName("assets")
public class Asset {
    @TableId(type = IdType.INPUT)
    private Long id;
    private Long ownerId;
    private String name;
    /** image / video / audio / text */
    private String assetType;
    private String mimeType;
    private Long sizeBytes;
    private String url;
    private String thumbnailUrl;
    private String storagePath;
    /** ready / processing / blocked */
    private String status;
    private Long enterpriseId;
    /** none / pending / approved / rejected (Seedance 2.0 认证) */
    private String certificationStatus;
    private String certificationReason;
    @TableLogic
    private Boolean deleted;
    private OffsetDateTime createdAt;
    private OffsetDateTime updatedAt;
}
