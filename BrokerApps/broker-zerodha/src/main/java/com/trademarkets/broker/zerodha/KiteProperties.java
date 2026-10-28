package com.trademarkets.broker.zerodha;

import java.time.LocalTime;
import java.time.ZoneId;

import org.springframework.boot.context.properties.ConfigurationProperties;

/** kite.* settings (zerodha.properties). Kite logins expire every day at tokenExpiryTime in zone. */
@ConfigurationProperties("kite")
public record KiteProperties(String apiUrl, String loginUrl, LocalTime tokenExpiryTime, ZoneId zone) {
}
