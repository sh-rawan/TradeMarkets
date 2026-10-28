package com.trademarkets.broker.common.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/** app.* settings. encryptionKey (secrets.properties) encrypts login tokens in the DB. */
@ConfigurationProperties("app")
public record AppProperties(String encryptionKey) {
}
