package com.trademarkets.broker.common.trading;

public class TradingDisabledException extends RuntimeException {

	public TradingDisabledException() {
		super("Trading is disabled. Set trading.enabled=true in trading.properties to place or modify orders.");
	}

}
