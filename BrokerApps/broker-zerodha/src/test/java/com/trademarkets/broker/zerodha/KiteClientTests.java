package com.trademarkets.broker.zerodha;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalTime;
import java.time.ZoneId;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import com.trademarkets.broker.common.broker.Broker;
import com.trademarkets.broker.common.broker.Broker.OrderRequest;
import com.trademarkets.broker.common.broker.Broker.OrderType;
import com.trademarkets.broker.common.broker.Broker.Session;
import com.trademarkets.broker.common.broker.Broker.Side;
import com.trademarkets.broker.common.broker.BrokerException;

import tools.jackson.databind.json.JsonMapper;

/** Kite API calls against a fake server, using response shapes from the Kite Connect docs. */
class KiteClientTests {

	private static final Session SESSION = new Session("main", "abc", "tok");

	private MockRestServiceServer server;
	private KiteClient client;

	@BeforeEach
	void setUp() {
		RestClient.Builder builder = RestClient.builder();
		server = MockRestServiceServer.bindTo(builder).build();
		var props = new KiteProperties("https://api.kite.trade", "https://kite.zerodha.com/connect/login",
				LocalTime.of(6, 0), ZoneId.of("Asia/Kolkata"));
		client = new KiteClient(props, JsonMapper.builder().build(), builder);
	}

	private void respond(String url, String data) {
		server.expect(requestTo(url))
				.andExpect(header("Authorization", "token abc:tok"))
				.andExpect(header("X-Kite-Version", "3"))
				.andRespond(withSuccess("{\"status\":\"success\",\"data\":" + data + "}", MediaType.APPLICATION_JSON));
	}

	@Test
	void checksumIsSha256OfKeyTokenSecret() {
		// sha256("abc" + "def" + "ghi") = sha256("abcdefghi")
		assertThat(KiteClient.checksum("abc", "def", "ghi"))
				.isEqualTo("19cc02f26df43cc571bc9ed7b0c4d29224a3ec229529221725ef76d021c8326f");
	}

	@Test
	void createSessionPostsChecksum() {
		server.expect(requestTo("https://api.kite.trade/session/token"))
				.andExpect(method(HttpMethod.POST))
				.andExpect(content().formDataContains(Map.of("api_key", "abc", "request_token", "def",
						"checksum", KiteClient.checksum("abc", "def", "ghi"))))
				.andRespond(withSuccess("""
						{"status":"success","data":{"user_id":"AB1234","user_name":"Test","access_token":"tok"}}""",
						MediaType.APPLICATION_JSON));

		KiteJson.Session session = client.createSession("abc", "ghi", "def");

		assertThat(session.userId()).isEqualTo("AB1234");
		assertThat(session.accessToken()).isEqualTo("tok");
		server.verify();
	}

	@Test
	void holdingsCountT1Shares() {
		respond("https://api.kite.trade/portfolio/holdings", """
				[{"tradingsymbol":"INFY","exchange":"NSE","isin":"INE009A01021","quantity":10,"t1_quantity":2,
				  "average_price":1400.5,"last_price":1550.25,"close_price":1540,"pnl":1497.5,
				  "day_change":10.25,"day_change_percentage":0.665,"product":"CNC"}]""");

		assertThat(client.holdings(SESSION)).singleElement().satisfies(h -> {
			assertThat(h.symbol()).isEqualTo("INFY");
			assertThat(h.quantity()).isEqualTo(12);
			assertThat(h.averagePrice()).isEqualByComparingTo("1400.5");
		});
	}

	@Test
	void fundsPerSegment() {
		respond("https://api.kite.trade/user/margins", """
				{"equity":{"enabled":true,"net":99725.05,"available":{"cash":245431.6,"live_balance":99725.05,
				  "collateral":0},"utilised":{"debits":145706.55}},
				 "commodity":{"enabled":false,"net":0,"available":{"cash":0},"utilised":{"debits":0}}}""");

		assertThat(client.funds(SESSION)).singleElement().satisfies(f -> {
			assertThat(f.segment()).isEqualTo("equity");
			assertThat(f.availableCash()).isEqualByComparingTo("245431.6");
			assertThat(f.usedMargin()).isEqualByComparingTo("145706.55");
		});
	}

	@Test
	void netPositions() {
		respond("https://api.kite.trade/portfolio/positions", """
				{"net":[{"tradingsymbol":"NIFTY26NOVFUT","exchange":"NFO","product":"NRML","quantity":75,
				  "average_price":24000,"last_price":24100,"pnl":7500}],"day":[]}""");

		assertThat(client.positions(SESSION)).singleElement()
				.satisfies(p -> assertThat(p.quantity()).isEqualTo(75));
	}

	@Test
	void ordersWithIstTimestamps() {
		respond("https://api.kite.trade/orders", """
				[{"order_id":"151220000000000","variety":"regular","status":"COMPLETE","tradingsymbol":"INFY",
				  "exchange":"NSE","transaction_type":"BUY","order_type":"LIMIT","product":"CNC","quantity":5,
				  "price":1450,"trigger_price":0,"filled_quantity":5,"average_price":1449.9,"status_message":null,
				  "tag":null,"order_timestamp":"2026-10-23 09:30:00","exchange_update_timestamp":null}]""");

		List<Broker.Order> orders = client.orders(SESSION);

		assertThat(orders).singleElement().satisfies(o -> {
			assertThat(o.status()).isEqualTo("COMPLETE");
			assertThat(o.filledQuantity()).isEqualTo(5);
			assertThat(o.placedAt()).isEqualTo(Instant.parse("2026-10-23T04:00:00Z")); // 09:30 IST
		});
	}

	@Test
	void placeOrderSendsKiteForm() {
		server.expect(requestTo("https://api.kite.trade/orders/regular"))
				.andExpect(method(HttpMethod.POST))
				.andExpect(header("Authorization", "token abc:tok"))
				.andExpect(content().formDataContains(Map.of("tradingsymbol", "INFY", "exchange", "NSE",
						"transaction_type", "SELL", "order_type", "SL-M", "quantity", "3", "product", "MIS",
						"validity", "DAY", "trigger_price", "1500")))
				.andRespond(withSuccess("""
						{"status":"success","data":{"order_id":"151220000000001"}}""", MediaType.APPLICATION_JSON));

		String id = client.placeOrder(SESSION, new OrderRequest("infy", "nse", Side.SELL, OrderType.SL_M, "mis", 3L,
				null, new BigDecimal("1500"), null, null, null));

		assertThat(id).isEqualTo("151220000000001");
		server.verify();
	}

	@Test
	void cancelLooksUpVarietyFirst() {
		respond("https://api.kite.trade/orders/151220000000002", """
				[{"order_id":"151220000000002","variety":"amo","status":"AMO REQ RECEIVED"}]""");
		server.expect(requestTo("https://api.kite.trade/orders/amo/151220000000002"))
				.andExpect(method(HttpMethod.DELETE))
				.andRespond(withSuccess("""
						{"status":"success","data":{"order_id":"151220000000002"}}""", MediaType.APPLICATION_JSON));

		assertThat(client.cancelOrder(SESSION, "151220000000002")).isEqualTo("151220000000002");
		server.verify();
	}

	@Test
	void tokenExceptionMeansLoginExpired() {
		server.expect(requestTo("https://api.kite.trade/portfolio/holdings"))
				.andRespond(withStatus(HttpStatus.FORBIDDEN).contentType(MediaType.APPLICATION_JSON).body("""
						{"status":"error","message":"Incorrect `api_key` or `access_token`.","error_type":"TokenException"}"""));

		assertThatThrownBy(() -> client.holdings(SESSION))
				.isInstanceOfSatisfying(BrokerException.class, e -> assertThat(e.isSessionExpired()).isTrue());
	}

	@Test
	void otherErrorsAreNotLoginProblems() {
		server.expect(requestTo("https://api.kite.trade/orders/regular"))
				.andRespond(withStatus(HttpStatus.BAD_REQUEST).contentType(MediaType.APPLICATION_JSON).body("""
						{"status":"error","message":"Insufficient funds.","error_type":"MarginException"}"""));

		assertThatThrownBy(() -> client.placeOrder(SESSION, new OrderRequest("INFY", "NSE", Side.BUY,
				OrderType.MARKET, "CNC", 1L, null, null, null, null, null)))
				.isInstanceOfSatisfying(BrokerException.class, e -> assertThat(e.isSessionExpired()).isFalse());
	}

}
