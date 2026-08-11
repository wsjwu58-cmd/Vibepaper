package com.vibepaper.common.config;

import com.baomidou.mybatisplus.annotation.DbType;
import com.baomidou.mybatisplus.extension.plugins.MybatisPlusInterceptor;
import com.baomidou.mybatisplus.extension.plugins.inner.OptimisticLockerInnerInterceptor;
import com.baomidou.mybatisplus.extension.plugins.inner.PaginationInnerInterceptor;
import com.fasterxml.jackson.databind.ser.std.ToStringSerializer;
import com.vibepaper.common.id.SnowflakeIdGenerator;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * 通用 Bean 装配：Snowflake、MyBatis-Plus 分页/乐观锁、Long→String（防 JS 精度丢失）。
 */
@Configuration
public class CommonConfig {

    @Bean
    public SnowflakeIdGenerator snowflakeIdGenerator(
            @Value("${vibepaper.snowflake.datacenter-id:1}") long datacenterId,
            @Value("${vibepaper.snowflake.worker-id:1}") long workerId) {
        return new SnowflakeIdGenerator(datacenterId, workerId);
    }

    /**
     * Snowflake Long 超出 Number.MAX_SAFE_INTEGER，必须序列化为字符串供前端使用。
     */
    @Bean
    public Jackson2ObjectMapperBuilderCustomizer longAsStringCustomizer() {
        return builder -> builder
                .serializerByType(Long.class, ToStringSerializer.instance)
                .serializerByType(Long.TYPE, ToStringSerializer.instance);
    }

    @Bean
    public MybatisPlusInterceptor mybatisPlusInterceptor() {
        MybatisPlusInterceptor interceptor = new MybatisPlusInterceptor();
        interceptor.addInnerInterceptor(new OptimisticLockerInnerInterceptor());
        PaginationInnerInterceptor pagination = new PaginationInnerInterceptor(DbType.POSTGRE_SQL);
        pagination.setMaxLimit(200L);
        interceptor.addInnerInterceptor(pagination);
        return interceptor;
    }
}
