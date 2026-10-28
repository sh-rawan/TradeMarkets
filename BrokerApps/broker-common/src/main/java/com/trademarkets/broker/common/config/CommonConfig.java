package com.trademarkets.broker.common.config;

import java.time.Clock;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@EnableScheduling
@EnableConfigurationProperties({ AppProperties.class, SyncProperties.class, TradingProperties.class })
public class CommonConfig {

	/** Injected instead of calling Instant.now() so tests can control time. */
	@Bean
	Clock clock() {
		return Clock.systemUTC();
	}

}
