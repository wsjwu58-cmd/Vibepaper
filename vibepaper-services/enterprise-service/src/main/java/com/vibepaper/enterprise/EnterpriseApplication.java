package com.vibepaper.enterprise;

import com.vibepaper.common.config.CommonConfig;
import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.client.discovery.EnableDiscoveryClient;
import org.springframework.cloud.openfeign.EnableFeignClients;
import org.springframework.context.annotation.Import;

@SpringBootApplication(scanBasePackages = {"com.vibepaper.common", "com.vibepaper.enterprise"})
@EnableDiscoveryClient
@EnableFeignClients
@MapperScan("com.vibepaper.enterprise.mapper")
@Import(CommonConfig.class)
public class EnterpriseApplication {
    public static void main(String[] args) {
        SpringApplication.run(EnterpriseApplication.class, args);
    }
}
