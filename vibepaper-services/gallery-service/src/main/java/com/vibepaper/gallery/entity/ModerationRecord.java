package com.vibepaper.gallery.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
@TableName("moderation_records")
public class ModerationRecord {
    @TableId(type = IdType.INPUT)
    private Long id;
    private Long publicationId;
    private Long operatorId;
    /** approve / reject / take_down */
    private String action;
    private String reason;
    private OffsetDateTime createdAt;
}
