package com.vibepaper.gallery.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
@TableName("publications")
public class Publication {
    @TableId(type = IdType.INPUT)
    private Long id;
    private Long canvasId;
    private Long ownerId;
    private String title;
    private String description;
    /** JSON array of tag strings */
    private String tags;
    /** pending / published / rejected / taken_down */
    private String status;
    private String thumbnailUrl;
    private String previewAssetUrl;
    /** JSON array of result asset URLs */
    private String resultAssetUrls;
    private Long viewCount;
    private String rejectedReason;
    private OffsetDateTime publishedAt;
    private OffsetDateTime createdAt;
}
