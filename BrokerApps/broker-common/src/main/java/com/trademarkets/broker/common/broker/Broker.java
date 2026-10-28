package com.trademarkets.broker.common.broker;

import java.math.BigDecimal;
import java.net.URI;
import java.time.Instant;
import java.util.List;
import java.util.Map;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

/**
 * A broker connector (Zerodha, Angel One, ...). It is code only: the accounts that use it are listed in
 * accounts.properties with accounts.&lt;name&gt;.broker=&lt;name()&gt;. Everything else (DB, sync, order safety checks,
 * REST API) lives in broker-common and works for any broker.
 * Implementations throw {@link BrokerException} for any broker-side error.
 */
public interface Broker {

	/** Upper-case id used in accounts.properties and stored with every account, e.g. "ZERODHA". */
	String name();

	// ---- login: a broker supports automatic login, a browser login, or neither (access-token in config) ----

	/** True if {@link #autoLogin} can log in without the user (e.g. with a TOTP secret). */
	default boolean supportsAutoLogin() {
		return false;
	}

	default Login autoLogin(String account, AccountConfig config) {
		throw new UnsupportedOperationException(name() + " has no automatic login");
	}

	/** True if the user logs in through the browser via {@link #loginUrl}. */
	default boolean supportsBrowserLogin() {
		return false;
	}

	/** Where to send the user's browser to log in, or null if this broker has no browser login. */
	default URI loginUrl(String account, AccountConfig config) {
		return null;
	}

	record Login(String userId, String userName, String accessToken, Instant expiresAt) {
		@Override
		public String toString() {
			return "Login[" + userId + "]"; // never log the token
		}
	}

	// ---- data and orders ----

	Profile profile(Session session);

	/** Cash and margin per segment (equity, commodity, ...). */
	List<Funds> funds(Session session);

	List<Holding> holdings(Session session);

	List<Position> positions(Session session);

	/** Today's orders. */
	List<Order> orders(Session session);

	/** Today's fills. */
	List<Trade> trades(Session session);

	/** Keys are instruments as EXCHANGE:SYMBOL, e.g. NSE:INFY. */
	Map<String, Quote> quotes(Session session, List<String> instruments);

	/** Returns the broker's order id. Must never retry: a retried order can end up placed twice. */
	String placeOrder(Session session, OrderRequest request);

	String modifyOrder(Session session, String orderId, ModifyRequest request);

	String cancelOrder(Session session, String orderId);

	/** Credentials for one call. */
	record Session(String account, String apiKey, String accessToken) {
		@Override
		public String toString() {
			return "Session[" + account + "]"; // never log the token
		}
	}

	record Profile(String userId, String userName, String email, List<String> exchanges) {
	}

	record Funds(String segment, BigDecimal availableCash, BigDecimal usedMargin, BigDecimal net) {
	}

	record Holding(String symbol, String exchange, String isin, long quantity, BigDecimal averagePrice,
			BigDecimal lastPrice, BigDecimal closePrice, BigDecimal pnl, BigDecimal dayChangePct) {
	}

	record Position(String symbol, String exchange, String product, long quantity, BigDecimal averagePrice,
			BigDecimal lastPrice, BigDecimal pnl) {
	}

	record Order(String orderId, String symbol, String exchange, String side, String orderType, String product,
			long quantity, BigDecimal price, BigDecimal triggerPrice, String status, long filledQuantity,
			BigDecimal averagePrice, String statusMessage, String tag, Instant placedAt, Instant updatedAt) {
	}

	record Trade(String tradeId, String orderId, String symbol, String exchange, String side, long quantity,
			BigDecimal price, Instant filledAt) {
	}

	record Quote(BigDecimal lastPrice, BigDecimal open, BigDecimal high, BigDecimal low, BigDecimal close,
			long volume) {
	}

	enum Side {
		BUY, SELL
	}

	/** SL = stop-loss limit, SL_M = stop-loss market. */
	enum OrderType {
		MARKET, LIMIT, SL, SL_M
	}

	/**
	 * A new order. price is needed for LIMIT and SL, triggerPrice for SL and SL_M.
	 * product is broker specific (Zerodha: CNC delivery, MIS intraday, NRML F&amp;O).
	 * validity defaults to DAY. afterMarket places an after-market order (AMO).
	 */
	record OrderRequest(@NotBlank String symbol, @NotBlank String exchange, @NotNull Side side,
			@NotNull OrderType type, @NotBlank String product, @NotNull @Positive Long quantity, @Positive BigDecimal price,
			@Positive BigDecimal triggerPrice, String validity, Boolean afterMarket, @Size(max = 20) String tag) {

		public boolean isAfterMarket() {
			return Boolean.TRUE.equals(afterMarket);
		}

	}

	/** Changes to an open order. Null fields are left as they are. */
	record ModifyRequest(OrderType type, @Positive Long quantity, @Positive BigDecimal price,
			@Positive BigDecimal triggerPrice) {
	}

}
