package com.vibepaper.identity.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
@TableName("user_preferences")
public class UserPreference {
    @TableId(type = IdType.INPUT)
    private Long userId;
    private String theme;
    private String language;
    private String defaultTextModel;
    private String defaultImageModel;
    private String defaultVideoModel;
    private String defaultResolution;
    private OffsetDateTime updatedAt;
}
