package com.trademarkets.broker.zerodha;

import java.math.BigDecimal;
import java.util.List;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

import tools.jackson.databind.PropertyNamingStrategies.SnakeCaseStrategy;
import tools.jackson.databind.annotation.JsonNaming;

/**
 * Kite Connect v3 response shapes (only the fields we use). All numbers are boxed because Kite
 * sends null for some of them. See https://kite.trade/docs/connect/v3/
 */
final class KiteJson {

	private KiteJson() {
	}

	/** Every Kite response: {"status":"success","data":...} or {"status":"error","message":..,"error_type":..}. */
	@JsonNaming(SnakeCaseStrategy.class)
	@JsonIgnoreProperties(ignoreUnknown = true)
	record Envelope<T>(String status, T data, String message, String errorType) {
	}

	@JsonNaming(SnakeCaseStrategy.class)
	@JsonIgnoreProperties(ignoreUnknown = true)
	record Session(String userId, String userName, String accessToken) {
		@Override
		public String toString() {
			return "Session[" + userId + "]"; // never log the token
		}
	}

	@JsonNaming(SnakeCaseStrategy.class)
	@JsonIgnoreProperties(ignoreUnknown = true)
	record Profile(String userId, String userName, String email, List<String> exchanges) {
	}

	@JsonNaming(SnakeCaseStrategy.class)
	@JsonIgnoreProperties(ignoreUnknown = true)
	record Margins(Segment equity, Segment commodity) {
	}

	@JsonNaming(SnakeCaseStrategy.class)
	@JsonIgnoreProperties(ignoreUnknown = true)
	record Segment(Boolean enabled, BigDecimal net, Available available, Utilised utilised) {
	}

	@JsonNaming(SnakeCaseStrategy.class)
	@JsonIgnoreProperties(ignoreUnknown = true)
	record Available(BigDecimal cash, BigDecimal liveBalance, BigDecimal collateral) {
	}

	@JsonNaming(SnakeCaseStrategy.class)
	@JsonIgnoreProperties(ignoreUnknown = true)
	record Utilised(BigDecimal debits) {
	}

	@JsonNaming(SnakeCaseStrategy.class)
	@JsonIgnoreProperties(ignoreUnknown = true)
	record Holding(String tradingsymbol, String exchange, String isin, Long quantity, Long t1Quantity,
			BigDecimal averagePrice, BigDecimal lastPrice, BigDecimal closePrice, BigDecimal pnl,
			BigDecimal dayChangePercentage) {
	}

	@JsonNaming(SnakeCaseStrategy.class)
	@JsonIgnoreProperties(ignoreUnknown = true)
	record Positions(List<Position> net, List<Position> day) {
	}

	@JsonNaming(SnakeCaseStrategy.class)
	@JsonIgnoreProperties(ignoreUnknown = true)
	record Position(String tradingsymbol, String exchange, String product, Long quantity, BigDecimal averagePrice,
			BigDecimal lastPrice, BigDecimal pnl) {
	}

	@JsonNaming(SnakeCaseStrategy.class)
	@JsonIgnoreProperties(ignoreUnknown = true)
	record Order(String orderId, String variety, String status, String tradingsymbol, String exchange,
			String transactionType, String orderType, String product, Long quantity, BigDecimal price,
			BigDecimal triggerPrice, Long filledQuantity, BigDecimal averagePrice, String statusMessage, String tag,
			String orderTimestamp, String exchangeUpdateTimestamp) {
	}

	@JsonNaming(SnakeCaseStrategy.class)
	@JsonIgnoreProperties(ignoreUnknown = true)
	record Trade(String tradeId, String orderId, String tradingsymbol, String exchange, String transactionType,
			Long quantity, BigDecimal averagePrice, String fillTimestamp) {
	}

	@JsonNaming(SnakeCaseStrategy.class)
	@JsonIgnoreProperties(ignoreUnknown = true)
	record Quote(BigDecimal lastPrice, Long volume, Ohlc ohlc) {
	}

	@JsonNaming(SnakeCaseStrategy.class)
	@JsonIgnoreProperties(ignoreUnknown = true)
	record Ohlc(BigDecimal open, BigDecimal high, BigDecimal low, BigDecimal close) {
	}

	@JsonNaming(SnakeCaseStrategy.class)
	@JsonIgnoreProperties(ignoreUnknown = true)
	record OrderId(String orderId) {
	}

}
