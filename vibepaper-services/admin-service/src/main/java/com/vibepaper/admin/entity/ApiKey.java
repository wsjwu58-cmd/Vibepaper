package com.vibepaper.admin.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
@TableName("api_keys")
public class ApiKey {
    @TableId(type = IdType.INPUT)
    private Long id;
    private String name;
    private String provider;
    private String keyCipher;
    private String baseUrl;
    private Boolean enabled;
    private Integer rateLimit;
    private String healthStatus;
    private OffsetDateTime lastCheckedAt;
    private OffsetDateTime createdAt;
}
