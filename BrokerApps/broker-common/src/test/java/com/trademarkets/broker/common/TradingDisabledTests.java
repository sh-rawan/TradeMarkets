package com.trademarkets.broker.common;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.springframework.test.web.servlet.MockMvc;

import com.trademarkets.broker.common.FakeBrokers.FakeBroker;

/** With trading.enabled=false nothing can be bought or sold, but open orders can still be cancelled. */
@SpringBootTest(properties = "trading.enabled=false")
@AutoConfigureMockMvc
class TradingDisabledTests {

	@Autowired
	MockMvc mvc;

	@MockitoSpyBean
	FakeBroker fake;

	@Test
	void placingIsBlocked() throws Exception {
		mvc.perform(post("/api/accounts/main/orders").contentType(MediaType.APPLICATION_JSON).content("""
				{"symbol":"INFY","exchange":"NSE","side":"BUY","type":"LIMIT","product":"CNC","quantity":1,"price":10}"""))
				.andExpect(status().isForbidden());
		verify(fake, never()).placeOrder(any(), any());
	}

	@Test
	void modifyingIsBlocked() throws Exception {
		mvc.perform(put("/api/accounts/main/orders/ord-1").contentType(MediaType.APPLICATION_JSON).content("""
				{"price":12}"""))
				.andExpect(status().isForbidden());
		verify(fake, never()).modifyOrder(any(), any(), any());
	}

	@Test
	void cancellingStillWorks() throws Exception {
		mvc.perform(delete("/api/accounts/main/orders/ord-1")).andExpect(status().isOk());
		verify(fake).cancelOrder(any(), any());
	}

}
