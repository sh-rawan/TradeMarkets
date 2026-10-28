package com.trademarkets.broker.common.broker;

/**
 * One account from accounts.properties, e.g.
 * <pre>
 * accounts.acc1.broker=ZERODHA
 * accounts.acc1.api-key=...
 * </pre>
 * Each broker uses the fields it needs:
 * Zerodha: apiKey, apiSecret. Angel One: apiKey, clientId, pin, totpSecret.
 * accessToken is for brokers that hand out long-lived tokens (skips login).
 */
public record AccountConfig(String broker, Boolean enabled, String apiKey, String apiSecret, String clientId,
		String pin, String totpSecret, String accessToken) {

	public boolean isEnabled() {
		return !Boolean.FALSE.equals(enabled);
	}

	@Override
	public String toString() {
		return "AccountConfig[broker=" + broker + ", apiKey=" + apiKey + "]"; // never log secrets
	}

}
