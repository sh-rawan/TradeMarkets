package com.trademarkets.broker.common;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Component;

import com.trademarkets.broker.common.broker.AccountConfig;
import com.trademarkets.broker.common.broker.Broker;

/** Two do-nothing brokers for tests; tests spy on them (@MockitoSpyBean) to return data. */
final class FakeBrokers {

	private FakeBrokers() {
	}

	/** Returns empty data for everything. */
	abstract static class EmptyBroker implements Broker {

		@Override
		public Profile profile(Session s) {
			return new Profile("U1", "Fake", null, List.of());
		}

		@Override
		public List<Funds> funds(Session s) {
			return List.of();
		}

		@Override
		public List<Holding> holdings(Session s) {
			return List.of();
		}

		@Override
		public List<Position> positions(Session s) {
			return List.of();
		}

		@Override
		public List<Order> orders(Session s) {
			return List.of();
		}

		@Override
		public List<Trade> trades(Session s) {
			return List.of();
		}

		@Override
		public Map<String, Quote> quotes(Session s, List<String> instruments) {
			return Map.of();
		}

		@Override
		public String placeOrder(Session s, OrderRequest request) {
			return "fake-order";
		}

		@Override
		public String modifyOrder(Session s, String orderId, ModifyRequest request) {
			return orderId;
		}

		@Override
		public String cancelOrder(Session s, String orderId) {
			return orderId;
		}

	}

	/** Needs a token or a login. */
	@Component
	static class FakeBroker extends EmptyBroker {

		@Override
		public String name() {
			return "FAKE";
		}

	}

	/** Logs in by itself, like Angel One with a TOTP secret. */
	@Component
	static class AutoBroker extends EmptyBroker {

		@Override
		public String name() {
			return "AUTO";
		}

		@Override
		public boolean supportsAutoLogin() {
			return true;
		}

		@Override
		public Login autoLogin(String account, AccountConfig config) {
			return new Login("AUTO1", "Auto User", "auto-token-" + System.nanoTime(), Instant.now().plusSeconds(3600));
		}

	}

}
