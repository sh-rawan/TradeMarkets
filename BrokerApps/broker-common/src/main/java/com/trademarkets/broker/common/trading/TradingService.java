package com.trademarkets.broker.common.trading;

import java.math.BigDecimal;
import java.time.Clock;
import java.util.List;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import com.trademarkets.broker.common.account.AccountService;
import com.trademarkets.broker.common.broker.Broker.ModifyRequest;
import com.trademarkets.broker.common.broker.Broker.OrderRequest;
import com.trademarkets.broker.common.broker.Broker.OrderType;
import com.trademarkets.broker.common.broker.Broker.Quote;
import com.trademarkets.broker.common.broker.BrokerException;
import com.trademarkets.broker.common.config.TradingProperties;
import com.trademarkets.broker.common.data.SnapshotStore;

/**
 * Places, modifies and cancels orders after the safety checks in trading.properties.
 * Every order action is written to the "orders" log.
 */
@Service
public class TradingService {

	private static final Logger log = LoggerFactory.getLogger("broker.orders");

	private final AccountService accounts;
	private final SnapshotStore store;
	private final TradingProperties props;
	private final Clock clock;

	TradingService(AccountService accounts, SnapshotStore store, TradingProperties props,
			Clock clock) {
		this.accounts = accounts;
		this.store = store;
		this.props = props;
		this.clock = clock;
	}

	public String place(String account, OrderRequest r) {
		requireEnabled();
		requirePrices(r.type(), r.price(), r.triggerPrice());
		checkValue(account, r);
		log.info("PLACE {}: {} {} {}:{} {} {} price={} trigger={}{}", account, r.side(), r.quantity(), r.exchange(),
				r.symbol(), r.type(), r.product(), r.price(), r.triggerPrice(), r.isAfterMarket() ? " (AMO)" : "");
		String orderId;
		try {
			orderId = accounts.call(account, (b, s) -> b.placeOrder(s, r));
		}
		catch (BrokerException e) {
			log.warn("PLACE {} rejected: {}", account, e.getMessage());
			throw e;
		}
		log.info("PLACED {}: order {}", account, orderId);
		store.recordPlacedOrder(accounts.account(account), orderId, r, clock.instant());
		return orderId;
	}

	public String modify(String account, String orderId, ModifyRequest m) {
		requireEnabled();
		if (m.type() != null) {
			requirePrices(m.type(), m.price(), m.triggerPrice());
		}
		log.info("MODIFY {}: order {} type={} qty={} price={} trigger={}", account, orderId, m.type(), m.quantity(),
				m.price(), m.triggerPrice());
		try {
			return accounts.call(account, (b, s) -> b.modifyOrder(s, orderId, m));
		}
		catch (BrokerException e) {
			log.warn("MODIFY {} order {} rejected: {}", account, orderId, e.getMessage());
			throw e;
		}
	}

	/** Allowed even when trading is disabled: cancelling only reduces risk. */
	public String cancel(String account, String orderId) {
		log.info("CANCEL {}: order {}", account, orderId);
		try {
			return accounts.call(account, (b, s) -> b.cancelOrder(s, orderId));
		}
		catch (BrokerException e) {
			log.warn("CANCEL {} order {} rejected: {}", account, orderId, e.getMessage());
			throw e;
		}
	}

	private void requireEnabled() {
		if (!props.enabled()) {
			throw new TradingDisabledException();
		}
	}

	private static void requirePrices(OrderType type, BigDecimal price, BigDecimal trigger) {
		if ((type == OrderType.LIMIT || type == OrderType.SL) && price == null) {
			throw new IllegalArgumentException(type + " orders need a price");
		}
		if ((type == OrderType.SL || type == OrderType.SL_M) && trigger == null) {
			throw new IllegalArgumentException(type + " orders need a triggerPrice");
		}
	}

	/** Rejects orders above trading.max-order-value. Market orders are valued at the last traded price. */
	private void checkValue(String account, OrderRequest r) {
		if (!props.hasMaxOrderValue()) {
			return;
		}
		BigDecimal price = r.price() != null ? r.price() : r.triggerPrice();
		if (price == null) {
			price = lastPrice(account, r.exchange() + ":" + r.symbol());
		}
		BigDecimal value = price.multiply(BigDecimal.valueOf(r.quantity()));
		if (value.compareTo(props.maxOrderValue()) > 0) {
			log.warn("PLACE {} blocked: value {} is over max-order-value {}", account, value, props.maxOrderValue());
			throw new IllegalArgumentException("Order value " + value.toPlainString() + " is over trading.max-order-value "
					+ props.maxOrderValue().toPlainString());
		}
	}

	private BigDecimal lastPrice(String account, String instrument) {
		try {
			Map<String, Quote> quotes = accounts.call(account, (b, s) -> b.quotes(s, List.of(instrument)));
			Quote quote = quotes.get(instrument);
			if (quote == null || quote.lastPrice() == null) {
				throw new BrokerException("no quote returned for " + instrument, false);
			}
			return quote.lastPrice();
		}
		catch (BrokerException e) {
			if (e.isSessionExpired()) {
				throw e;
			}
			throw new IllegalArgumentException("Couldn't get a price for " + instrument
					+ " to check trading.max-order-value (" + e.getMessage() + "). Use a LIMIT order instead.");
		}
	}

}
