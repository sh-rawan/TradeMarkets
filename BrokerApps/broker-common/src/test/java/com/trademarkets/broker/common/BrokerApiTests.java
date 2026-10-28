package com.trademarkets.broker.common;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.springframework.test.web.servlet.MockMvc;

import com.trademarkets.broker.common.FakeBrokers.AutoBroker;
import com.trademarkets.broker.common.FakeBrokers.FakeBroker;
import com.trademarkets.broker.common.account.AccountService;
import com.trademarkets.broker.common.broker.Broker;
import com.trademarkets.broker.common.broker.BrokerException;
import com.trademarkets.broker.common.data.FundsRepository;
import com.trademarkets.broker.common.data.HoldingRepository;
import com.trademarkets.broker.common.data.OrderRepository;
import com.trademarkets.broker.common.data.PositionRepository;
import com.trademarkets.broker.common.data.SnapshotStore;
import com.trademarkets.broker.common.data.SyncService;

/**
 * The shared REST API, sync and order checks, with accounts on two fake brokers (see application.properties):
 * main/second/off on FAKE, auto on AUTO.
 */
@SpringBootTest
@AutoConfigureMockMvc
class BrokerApiTests {

	@Autowired
	MockMvc mvc;

	@MockitoSpyBean
	FakeBroker fake;

	@MockitoSpyBean
	AutoBroker auto;

	@Autowired
	AccountService accounts;

	@Autowired
	SyncService sync;

	@Autowired
	SnapshotStore store;

	@Autowired
	FundsRepository funds;

	@Autowired
	HoldingRepository holdings;

	@Autowired
	PositionRepository positions;

	@Autowired
	OrderRepository orders;

	@BeforeEach
	void brokerData() {
		doReturn(List.of(new Broker.Funds("equity", bd("50000"), bd("1000"), bd("49000")))).when(fake).funds(any());
		doReturn(List.of(
				new Broker.Holding("INFY", "NSE", "INE009A01021", 10, bd("1400"), bd("1500"), bd("1490"), bd("1000"),
						bd("0.67")),
				new Broker.Holding("TCS", "NSE", "INE467B01029", 5, bd("3500"), bd("3600"), bd("3610"), bd("500"),
						bd("-0.28"))))
				.when(fake).holdings(any());
		doReturn(List.of(new Broker.Position("NIFTY26NOVFUT", "NFO", "NRML", 75, bd("24000"), bd("24100"),
				bd("7500")))).when(fake).positions(any());
		doReturn(List.of(new Broker.Order("ord-1", "INFY", "NSE", "BUY", "LIMIT", "CNC", 10, bd("1400"), null,
				"COMPLETE", 10, bd("1400"), null, null, Instant.now(), Instant.now()))).when(fake).orders(any());
	}

	@Test
	void listsAllAccountsWithTheirBrokerAndLoginState() throws Exception {
		mvc.perform(get("/api/accounts"))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.length()").value(4))
				.andExpect(jsonPath("$[?(@.name=='main')].broker").value("FAKE"))
				.andExpect(jsonPath("$[?(@.name=='main')].login").value("TOKEN"))
				.andExpect(jsonPath("$[?(@.name=='second')].loggedIn").value(false))
				.andExpect(jsonPath("$[?(@.name=='auto')].broker").value("AUTO"))
				.andExpect(jsonPath("$[?(@.name=='auto')].login").value("AUTOMATIC"))
				.andExpect(jsonPath("$[?(@.name=='off')].enabled").value(false));
		mvc.perform(get("/api/info"))
				.andExpect(jsonPath("$.brokers.length()").value(2))
				.andExpect(jsonPath("$.accounts.length()").value(3)); // enabled only
	}

	@Test
	void unknownAccountIs404() throws Exception {
		mvc.perform(get("/api/accounts/nobody/holdings")).andExpect(status().isNotFound());
	}

	@Test
	void disabledAccountIs400() throws Exception {
		mvc.perform(get("/api/accounts/off/holdings")).andExpect(status().isBadRequest());
	}

	@Test
	void callsGoToTheAccountsBroker() throws Exception {
		mvc.perform(get("/api/accounts/main/holdings"))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.length()").value(2))
				.andExpect(jsonPath("$[0].symbol").value("INFY"));
		verify(fake).holdings(argThat(s -> s.account().equals("main") && s.accessToken().equals("token-main")));

		mvc.perform(get("/api/accounts/auto/holdings")).andExpect(status().isOk())
				.andExpect(jsonPath("$.length()").value(0));
		verify(auto).holdings(argThat(s -> s.account().equals("auto")));
	}

	@Test
	void accountThatIsNotLoggedInIs401() throws Exception {
		mvc.perform(get("/api/accounts/second/funds")).andExpect(status().isUnauthorized());
		verify(fake, never()).funds(any());
	}

	@Test
	void expiredLoginIsClearedAnd401() throws Exception {
		accounts.saveLogin("second", new Broker.Login("AB1234", "Test", "old-token", Instant.now().plusSeconds(3600)));
		doThrow(new BrokerException("token expired", true)).when(fake).positions(any());

		mvc.perform(get("/api/accounts/second/positions")).andExpect(status().isUnauthorized());

		assertThat(accounts.view("second").loggedIn()).isFalse();
	}

	@Test
	void automaticBrokerLogsInByItselfAndAgainWhenExpired() throws Exception {
		accounts.logout("auto");

		mvc.perform(get("/api/accounts/auto/funds")).andExpect(status().isOk());
		verify(auto).autoLogin(any(), any());
		assertThat(accounts.view("auto").loggedIn()).isTrue();

		// Broker says the token is no longer valid -> log in again and retry once.
		doThrow(new BrokerException("token expired", true)).doReturn(List.of()).when(auto).positions(any());
		mvc.perform(get("/api/accounts/auto/positions")).andExpect(status().isOk());
		verify(auto, times(2)).autoLogin(any(), any());
	}

	@Test
	void loginEndpointLogsInAutomaticBrokers() throws Exception {
		mvc.perform(get("/api/accounts/auto/login"))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.loggedIn").value(true))
				.andExpect(jsonPath("$.userId").value("AUTO1"));
	}

	@Test
	void syncStoresSnapshotsAndUpdatesOrdersInPlace() throws Exception {
		long fundsBefore = funds.count();
		long holdingsBefore = holdings.count();
		long positionsBefore = positions.count();

		mvc.perform(post("/api/accounts/main/sync"))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.ok").value(true))
				.andExpect(jsonPath("$.holdings").value(2));
		long ordersAfterFirst = orders.count();
		mvc.perform(post("/api/accounts/main/sync")).andExpect(jsonPath("$.ok").value(true));

		assertThat(funds.count()).isEqualTo(fundsBefore + 2);
		assertThat(holdings.count()).isEqualTo(holdingsBefore + 4);
		assertThat(positions.count()).isEqualTo(positionsBefore + 2);
		assertThat(orders.count()).isEqualTo(ordersAfterFirst); // same order id -> updated, not duplicated
		assertThat(accounts.view("main").lastSyncOk()).isTrue();
	}

	@Test
	void syncAllCoversEnabledAccountsOfAllBrokers() throws Exception {
		mvc.perform(post("/api/sync"))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.length()").value(3))
				.andExpect(jsonPath("$[?(@.account=='main')].ok").value(true))
				.andExpect(jsonPath("$[?(@.account=='second')].ok").value(false))
				.andExpect(jsonPath("$[?(@.account=='auto')].ok").value(true));
	}

	@Test
	void oldSnapshotsAreDeleted() {
		store.save(accounts.account("main"), Instant.now().minusSeconds(200L * 24 * 3600),
				fake.funds(null), fake.holdings(null), List.of(), List.of());

		assertThat(sync.deleteOldSnapshots()).isEqualTo(3);
	}

	@Test
	void placesLimitOrderAndRecordsIt() throws Exception {
		doReturn("ord-new").when(fake).placeOrder(any(), any());

		mvc.perform(post("/api/accounts/main/orders").contentType(MediaType.APPLICATION_JSON).content("""
				{"symbol":"INFY","exchange":"NSE","side":"BUY","type":"LIMIT","product":"CNC","quantity":5,"price":1450}"""))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.orderId").value("ord-new"));

		assertThat(orders.findByAccountAndOrderId(accounts.account("main"), "ord-new"))
				.hasValueSatisfying(o -> assertThat(o.isPlacedByApp()).isTrue());
	}

	@Test
	void limitOrderWithoutPriceIs400() throws Exception {
		mvc.perform(post("/api/accounts/main/orders").contentType(MediaType.APPLICATION_JSON).content("""
				{"symbol":"INFY","exchange":"NSE","side":"BUY","type":"LIMIT","product":"CNC","quantity":5}"""))
				.andExpect(status().isBadRequest());
		verify(fake, never()).placeOrder(any(), any());
	}

	@Test
	void invalidOrderIs400() throws Exception {
		mvc.perform(post("/api/accounts/main/orders").contentType(MediaType.APPLICATION_JSON).content("""
				{"symbol":"","exchange":"NSE","side":"BUY","type":"MARKET","product":"CNC","quantity":0}"""))
				.andExpect(status().isBadRequest());
		verify(fake, never()).placeOrder(any(), any());
	}

	@Test
	void orderOverMaxValueIsBlocked() throws Exception {
		// 1000 x 500 = 500000 > trading.max-order-value 100000
		mvc.perform(post("/api/accounts/main/orders").contentType(MediaType.APPLICATION_JSON).content("""
				{"symbol":"INFY","exchange":"NSE","side":"BUY","type":"LIMIT","product":"CNC","quantity":1000,"price":500}"""))
				.andExpect(status().isBadRequest());
		verify(fake, never()).placeOrder(any(), any());
	}

	@Test
	void marketOrderIsValuedAtLastPrice() throws Exception {
		doReturn(Map.of("NSE:INFY", new Broker.Quote(bd("1500"), bd("1490"), bd("1510"), bd("1480"), bd("1490"), 1000)))
				.when(fake).quotes(any(), anyList());
		doReturn("ord-mkt").when(fake).placeOrder(any(), any());

		// 100 x 1500 = 150000 > 100000 -> blocked
		mvc.perform(post("/api/accounts/main/orders").contentType(MediaType.APPLICATION_JSON).content("""
				{"symbol":"INFY","exchange":"NSE","side":"SELL","type":"MARKET","product":"CNC","quantity":100}"""))
				.andExpect(status().isBadRequest());
		// 10 x 1500 = 15000 -> placed
		mvc.perform(post("/api/accounts/main/orders").contentType(MediaType.APPLICATION_JSON).content("""
				{"symbol":"INFY","exchange":"NSE","side":"SELL","type":"MARKET","product":"CNC","quantity":10}"""))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.orderId").value("ord-mkt"));
	}

	private static BigDecimal bd(String s) {
		return new BigDecimal(s);
	}

}
