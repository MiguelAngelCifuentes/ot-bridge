package com.otbridge.api.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.servers.Server;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.List;

@Configuration
public class OpenApiConfig {

    @Bean
    public OpenAPI plantApiOpenApi() {
        return new OpenAPI()
                .info(new Info()
                        .title("OT-Bridge Plant API")
                        .version("1.0")
                        .description("API REST de la capa IT (PERA L3): máquinas, sensores, alarmas y umbrales de la planta simulada."))
                .servers(List.of(new Server().url("/")));
    }
}
