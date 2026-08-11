package com.vibepaper.admin.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
@TableName("announcements")
public class Announcement {
    @TableId(type = IdType.INPUT)
    private Long id;
    private String title;
    private String content;
    /** draft / published / taken_down */
    private String status;
    private OffsetDateTime publishedAt;
    private OffsetDateTime createdAt;
}
