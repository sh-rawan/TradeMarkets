package com.trademarkets.broker.angelone;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.jsonPath;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZoneOffset;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import com.trademarkets.broker.common.broker.AccountConfig;
import com.trademarkets.broker.common.broker.Broker.Login;
import com.trademarkets.broker.common.broker.Broker.OrderRequest;
import com.trademarkets.broker.common.broker.Broker.OrderType;
import com.trademarkets.broker.common.broker.Broker.Session;
import com.trademarkets.broker.common.broker.Broker.Side;
import com.trademarkets.broker.common.broker.BrokerException;

import tools.jackson.databind.json.JsonMapper;

/** SmartAPI calls against a fake server, using response shapes from the SmartAPI docs. */
class AngelOneClientTests {

	private static final String BASE = "https://apiconnect.angelone.in";
	private static final Session SESSION = new Session("acc3", "key", "jwt");
	private static final String SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ";
	private static final Instant NOW = Instant.parse("2026-10-26T04:00:00Z"); // 09:30 IST

	private MockRestServiceServer server;
	private AngelOneClient client;

	@BeforeEach
	void setUp() {
		RestClient.Builder builder = RestClient.builder();
		server = MockRestServiceServer.bindTo(builder).build();
		var props = new AngelOneProperties(BASE, LocalTime.MIDNIGHT, ZoneId.of("Asia/Kolkata"), "10.0.0.5",
				"1.2.3.4", "AA:BB:CC:DD:EE:FF");
		client = new AngelOneClient(props, JsonMapper.builder().build(), Clock.fixed(NOW, ZoneOffset.UTC), builder);
	}

	private void respond(HttpMethod method, String path, String data) {
		server.expect(requestTo(BASE + path))
				.andExpect(method(method))
				.andExpect(header("Authorization", "Bearer jwt"))
				.andExpect(header("X-PrivateKey", "key"))
				.andRespond(withSuccess("{\"status\":true,\"message\":\"SUCCESS\",\"errorcode\":\"\",\"data\":" + data
						+ "}", MediaType.APPLICATION_JSON));
	}

	@Test
	void logsInWithClientCodePinAndTotp() {
		server.expect(requestTo(BASE + "/rest/auth/angelbroking/user/v1/loginByPassword"))
				.andExpect(method(HttpMethod.POST))
				.andExpect(header("X-PrivateKey", "key"))
				.andExpect(header("X-ClientPublicIP", "1.2.3.4"))
				.andExpect(jsonPath("$.clientcode").value("A123"))
				.andExpect(jsonPath("$.password").value("1234"))
				.andExpect(jsonPath("$.totp").value(Totp.code(SECRET, NOW)))
				.andRespond(withSuccess("""
						{"status":true,"message":"SUCCESS","errorcode":"","data":{"jwtToken":"Bearer jwt",
						 "refreshToken":"r","feedToken":"f"}}""", MediaType.APPLICATION_JSON));
		respond(HttpMethod.GET, "/rest/secure/angelbroking/user/v1/getProfile", """
				{"clientcode":"A123","name":"Test User","email":"","exchanges":"[\\"NSE\\",\\"BSE\\"]"}""");

		Login login = client.autoLogin("acc3",
				new AccountConfig("ANGELONE", null, "key", null, "A123", "1234", SECRET, null));

		assertThat(login.accessToken()).isEqualTo("jwt");
		assertThat(login.userId()).isEqualTo("A123");
		assertThat(login.userName()).isEqualTo("Test User");
		assertThat(login.expiresAt()).isEqualTo(Instant.parse("2026-10-26T18:30:00Z")); // next midnight IST
		server.verify();
	}

	@Test
	void missingCredentialsAreReported() {
		assertThatThrownBy(() -> client.autoLogin("acc3",
				new AccountConfig("ANGELONE", null, "key", null, "A123", null, SECRET, null)))
				.isInstanceOf(BrokerException.class)
				.hasMessageContaining("accounts.acc3.pin");
	}

	@Test
	void holdingsWithStringNumbers() {
		respond(HttpMethod.GET, "/rest/secure/angelbroking/portfolio/v1/getHolding", """
				[{"tradingsymbol":"TATASTEEL-EQ","exchange":"NSE","isin":"INE081A01020","t1quantity":"1",
				  "realisedquantity":"2","quantity":"2","product":"DELIVERY","averageprice":"111.87","ltp":"130.15",
				  "symboltoken":"3499","close":"129.6","profitandloss":"37","pnlpercentage":"16.34"}]""");

		assertThat(client.holdings(SESSION)).singleElement().satisfies(h -> {
			assertThat(h.symbol()).isEqualTo("TATASTEEL");
			assertThat(h.quantity()).isEqualTo(3);
			assertThat(h.averagePrice()).isEqualByComparingTo("111.87");
		});
	}

	@Test
	void fundsFromRms() {
		respond(HttpMethod.GET, "/rest/secure/angelbroking/user/v1/getRMS", """
				{"net":"9999999999999","availablecash":"10000.50","utiliseddebits":"250"}""");

		assertThat(client.funds(SESSION)).singleElement()
				.satisfies(f -> assertThat(f.availableCash()).isEqualByComparingTo("10000.50"));
	}

	@Test
	void emptyOrderBookIsNull() {
		respond(HttpMethod.GET, "/rest/secure/angelbroking/order/v1/getOrderBook", "null");

		assertThat(client.orders(SESSION)).isEmpty();
	}

	@Test
	void ordersAreMappedToCommonNames() {
		respond(HttpMethod.GET, "/rest/secure/angelbroking/order/v1/getOrderBook", """
				[{"variety":"STOPLOSS","ordertype":"STOPLOSS_LIMIT","producttype":"INTRADAY","duration":"DAY",
				  "price":"194.00","triggerprice":"193.5","quantity":"1","tradingsymbol":"SBIN-EQ",
				  "transactiontype":"BUY","exchange":"NSE","symboltoken":"3045","averageprice":"0",
				  "filledshares":"0","orderid":"201020000000080","text":"","status":"open","orderstatus":"open",
				  "updatetime":"26-Oct-2026 09:31:00","exchorderupdatetime":"26-Oct-2026 09:31:01"}]""");

		assertThat(client.orders(SESSION)).singleElement().satisfies(o -> {
			assertThat(o.symbol()).isEqualTo("SBIN");
			assertThat(o.orderType()).isEqualTo("SL");
			assertThat(o.product()).isEqualTo("MIS");
			assertThat(o.status()).isEqualTo("OPEN");
			assertThat(o.placedAt()).isEqualTo(Instant.parse("2026-10-26T04:01:00Z"));
		});
	}

	@Test
	void placeOrderLooksUpSymbolTokenAndMapsProduct() {
		respond(HttpMethod.POST, "/rest/secure/angelbroking/order/v1/searchScrip", """
				[{"exchange":"NSE","tradingsymbol":"SBIN-BE","symboltoken":"4884"},
				 {"exchange":"NSE","tradingsymbol":"SBIN-EQ","symboltoken":"3045"}]""");
		server.expect(requestTo(BASE + "/rest/secure/angelbroking/order/v1/placeOrder"))
				.andExpect(jsonPath("$.variety").value("NORMAL"))
				.andExpect(jsonPath("$.tradingsymbol").value("SBIN-EQ"))
				.andExpect(jsonPath("$.symboltoken").value("3045"))
				.andExpect(jsonPath("$.ordertype").value("LIMIT"))
				.andExpect(jsonPath("$.producttype").value("DELIVERY"))
				.andExpect(jsonPath("$.price").value("800"))
				.andExpect(jsonPath("$.quantity").value("2"))
				.andRespond(withSuccess("""
						{"status":true,"message":"SUCCESS","errorcode":"","data":{"script":"SBIN-EQ",
						 "orderid":"201020000000081","uniqueorderid":"u1"}}""", MediaType.APPLICATION_JSON));

		String id = client.placeOrder(SESSION, new OrderRequest("SBIN", "NSE", Side.BUY, OrderType.LIMIT, "CNC", 2L,
				new BigDecimal("800"), null, null, null, null));

		assertThat(id).isEqualTo("201020000000081");
		server.verify();
	}

	@Test
	void invalidTokenMeansLoginAgain() {
		server.expect(requestTo(BASE + "/rest/secure/angelbroking/portfolio/v1/getHolding"))
				.andRespond(withStatus(HttpStatus.FORBIDDEN).contentType(MediaType.APPLICATION_JSON).body("""
						{"success":false,"message":"Invalid Token","errorCode":"AG8001","data":""}"""));

		assertThatThrownBy(() -> client.holdings(SESSION))
				.isInstanceOfSatisfying(BrokerException.class, e -> assertThat(e.isSessionExpired()).isTrue());
	}

	@Test
	void otherErrorsAreNotLoginProblems() {
		server.expect(requestTo(BASE + "/rest/secure/angelbroking/user/v1/getRMS"))
				.andRespond(withSuccess("""
						{"status":false,"message":"Something went wrong","errorcode":"AB1004","data":null}""",
						MediaType.APPLICATION_JSON));

		assertThatThrownBy(() -> client.funds(SESSION))
				.isInstanceOfSatisfying(BrokerException.class, e -> assertThat(e.isSessionExpired()).isFalse());
	}

}
