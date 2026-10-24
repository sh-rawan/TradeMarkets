package com.trademarkets.viber;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(ViberProperties.class)
public class ViberBotApplication {

	public static void main(String[] args) {
		SpringApplication.run(ViberBotApplication.class, args);
	}

}
