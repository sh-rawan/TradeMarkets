package com.trademarkets.viber;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

class ViberClientTests {

	private MockRestServiceServer server;
	private ViberClient client;

	@BeforeEach
	void setUp() {
		RestClient.Builder builder = RestClient.builder();
		server = MockRestServiceServer.bindTo(builder).build();
		client = new ViberClient(new ViberProperties("https://chatapi.viber.com/pa/", "TestBot", "reply", "test-token", ""), builder);
	}

	@Test
	void sendTextPostsMessageToViber() {
		server.expect(requestTo("https://chatapi.viber.com/pa/send_message"))
				.andExpect(method(HttpMethod.POST))
				.andExpect(header("X-Viber-Auth-Token", "test-token"))
				.andExpect(content().json("""
						{"receiver":"user-1","type":"text","text":"any text","sender":{"name":"TestBot"}}"""))
				.andRespond(withSuccess("{\"status\":0,\"status_message\":\"ok\"}", MediaType.APPLICATION_JSON));

		String response = client.sendText("user-1", "any text");

		assertThat(response).contains("\"status\":0");
		server.verify();
	}

	@Test
	void setWebhookPostsUrlToViber() {
		server.expect(requestTo("https://chatapi.viber.com/pa/set_webhook"))
				.andExpect(method(HttpMethod.POST))
				.andExpect(content().json("{\"url\":\"https://example.ngrok-free.app\"}"))
				.andRespond(withSuccess("{\"status\":0}", MediaType.APPLICATION_JSON));

		client.setWebhook("https://example.ngrok-free.app");

		server.verify();
	}

}
