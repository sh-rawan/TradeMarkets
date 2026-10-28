package com.trademarkets.broker.angelone;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

/** Registers the angelone.* settings (brokers.properties). */
@Configuration
@EnableConfigurationProperties(AngelOneProperties.class)
class AngelOneConfig {
}
