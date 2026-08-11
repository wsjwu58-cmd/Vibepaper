package com.vibepaper.canvas;

import com.vibepaper.common.config.CommonConfig;
import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.client.discovery.EnableDiscoveryClient;
import org.springframework.context.annotation.Import;

@SpringBootApplication(scanBasePackages = {"com.vibepaper.common", "com.vibepaper.canvas"})
@EnableDiscoveryClient
@MapperScan("com.vibepaper.canvas.mapper")
@Import(CommonConfig.class)
public class CanvasApplication {
    public static void main(String[] args) {
        SpringApplication.run(CanvasApplication.class, args);
    }
}
