package com.trademarkets.broker.zerodha;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

/** Registers the kite.* settings (brokers.properties). */
@Configuration
@EnableConfigurationProperties(KiteProperties.class)
class ZerodhaConfig {
}
