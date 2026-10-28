package com.trademarkets.broker.angelone;

import java.time.LocalTime;
import java.time.ZoneId;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * angelone.* settings (brokers.properties). SmartAPI wants the caller's IPs and MAC address in every request;
 * leave them empty to detect them automatically. Set public-ip to your static IP if you registered one.
 */
@ConfigurationProperties("angelone")
public record AngelOneProperties(String apiUrl, LocalTime tokenExpiryTime, ZoneId zone, String localIp,
		String publicIp, String macAddress) {
}
