package com.vibepaper.enterprise.config;

import com.vibepaper.common.feign.FeignHeaderInterceptor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class FeignConfig {
    @Bean
    public FeignHeaderInterceptor feignHeaderInterceptor() {
        return new FeignHeaderInterceptor();
    }
}
