package com.trademarkets.broker;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.springframework.test.web.servlet.MockMvc;

import com.trademarkets.broker.angelone.AngelOneClient;
import com.trademarkets.broker.common.account.AccountService;
import com.trademarkets.broker.common.broker.Broker;
import com.trademarkets.broker.zerodha.KiteClient;
import com.trademarkets.broker.zerodha.KiteTestAccess;

/**
 * The whole app with both connectors and one account each (test application.properties).
 * Network calls of the connectors are stubbed.
 */
@SpringBootTest
@AutoConfigureMockMvc
class BrokerAppTests {

	@Autowired
	MockMvc mvc;

	@Autowired
	AccountService accounts;

	@MockitoSpyBean
	KiteClient kite;

	@MockitoSpyBean
	AngelOneClient angel;

	@BeforeEach
	void noNetwork() {
		for (Broker b : List.of(kite, angel)) {
			doReturn(List.of()).when(b).funds(any());
			doReturn(List.of()).when(b).holdings(any());
			doReturn(List.of()).when(b).positions(any());
			doReturn(List.of()).when(b).orders(any());
		}
		doReturn(new Broker.Login("A123", "Angel User", "angel-jwt", Instant.now().plusSeconds(3600)))
				.when(angel).autoLogin(any(), any());
	}

	@Test
	void bothBrokersAndTheirAccountsAreLoaded() throws Exception {
		mvc.perform(get("/api/info"))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.brokers.length()").value(2))
				.andExpect(jsonPath("$.accounts.length()").value(2));
		mvc.perform(get("/api/accounts"))
				.andExpect(jsonPath("$[?(@.name=='zer1')].broker").value("ZERODHA"))
				.andExpect(jsonPath("$[?(@.name=='zer1')].login").value("BROWSER"))
				.andExpect(jsonPath("$[?(@.name=='ang1')].broker").value("ANGELONE"))
				.andExpect(jsonPath("$[?(@.name=='ang1')].login").value("AUTOMATIC"));
	}

	@Test
	void eachAccountGoesToItsOwnBroker() throws Exception {
		doReturn(List.of(new Broker.Holding("SBIN", "NSE", null, 5, BigDecimal.ONE, BigDecimal.TEN, null, null, null)))
				.when(angel).holdings(any());

		mvc.perform(get("/api/accounts/ang1/holdings"))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$[0].symbol").value("SBIN"));

		verify(angel).holdings(argThat(s -> "angel-jwt".equals(s.accessToken())));
		accounts.logout("zer1");
		mvc.perform(get("/api/accounts/zer1/holdings")).andExpect(status().isUnauthorized()); // no daily login yet
	}

	@Test
	void zerodhaLoginRedirectsToKite() throws Exception {
		var result = mvc.perform(get("/api/accounts/zer1/login")).andExpect(status().isFound()).andReturn();

		assertThat(result.getResponse().getHeader("Location"))
				.startsWith("https://kite.zerodha.com/connect/login?v=3&api_key=test-key")
				.contains("redirect_params=account%3Dzer1");
	}

	@Test
	void zerodhaCallbackSavesLogin() throws Exception {
		KiteTestAccess.stubSession(kite, "test-key", "test-secret", "req-123", "AB1234", "access-xyz");

		mvc.perform(get("/api/kite/callback").param("account", "zer1").param("request_token", "req-123")
				.param("status", "success"))
				.andExpect(status().isOk());

		var view = accounts.view("zer1");
		assertThat(view.loggedIn()).isTrue();
		assertThat(view.userId()).isEqualTo("AB1234");
		assertThat(view.tokenExpiresAt()).isAfter(Instant.now());
	}

	@Test
	void zerodhaCallbackRejectsOtherBrokersAccounts() throws Exception {
		mvc.perform(get("/api/kite/callback").param("account", "ang1").param("request_token", "x")
				.param("status", "success"))
				.andExpect(status().isBadRequest());
	}

	@Test
	void cancelledZerodhaLoginIs400() throws Exception {
		mvc.perform(get("/api/kite/callback").param("account", "zer1").param("status", "cancelled"))
				.andExpect(status().isBadRequest());
	}

	@Test
	void angelLoginEndpointLogsInDirectly() throws Exception {
		mvc.perform(get("/api/accounts/ang1/login"))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.loggedIn").value(true));
		verify(angel).autoLogin(eq("ang1"), any());
	}

}
