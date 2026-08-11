package com.vibepaper.enterprise.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
@TableName("allocation_records")
public class AllocationRecord {
    @TableId(type = IdType.INPUT)
    private Long id;
    private Long enterpriseId;
    private Long operatorId;
    private Long memberId;
    /** allocate / recycle */
    private String allocType;
    private Integer points;
    private Integer balanceAfter;
    private OffsetDateTime createdAt;
}
