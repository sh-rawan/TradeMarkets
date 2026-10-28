package com.trademarkets.broker.common.config;

import java.math.BigDecimal;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * trading.* settings (trading.properties).
 * enabled=false blocks placing and modifying orders (cancelling is always allowed).
 * maxOrderValue rejects any order worth more than this (quantity x price); empty or 0 = no limit.
 */
@ConfigurationProperties("trading")
public record TradingProperties(boolean enabled, BigDecimal maxOrderValue) {

	public boolean hasMaxOrderValue() {
		return maxOrderValue != null && maxOrderValue.signum() > 0;
	}

}
