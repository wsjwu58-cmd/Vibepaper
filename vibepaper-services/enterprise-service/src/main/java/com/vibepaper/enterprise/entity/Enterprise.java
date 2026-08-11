package com.vibepaper.enterprise.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
@TableName("enterprises")
public class Enterprise {
    @TableId(type = IdType.INPUT)
    private Long id;
    private String name;
    private Long ownerId;
    private String enterpriseCode;
    private Integer totalPoints;
    private Integer allocatablePoints;
    private Boolean sharedPoolEnabled;
    private Boolean adminCanViewContent;
    private String status;
    private OffsetDateTime createdAt;
    private OffsetDateTime updatedAt;
}
