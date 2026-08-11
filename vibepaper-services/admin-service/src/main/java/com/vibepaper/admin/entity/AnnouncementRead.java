package com.vibepaper.admin.entity;

import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
@TableName("announcement_reads")
public class AnnouncementRead {
    private Long userId;
    private Long announcementId;
    private OffsetDateTime readAt;
}
