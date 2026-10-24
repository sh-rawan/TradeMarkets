package com.trademarkets.viber;

import org.springframework.boot.context.properties.ConfigurationProperties;

/** Values from viber.properties and secrets.properties. */
@ConfigurationProperties(prefix = "viber")
public record ViberProperties(String apiUrl, String botName, String replyText, String authToken, String webhookUrl) {
}
