package com.trademarkets.viber;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(ViberWebhookController.class)
class ViberWebhookControllerTests {

	private static final String TOKEN = "test-token"; // from src/test/resources/application.properties

	private static final String MESSAGE_EVENT = """
			{"event":"message","timestamp":1,"message_token":5,
			 "sender":{"id":"user-1","name":"Alice"},
			 "message":{"type":"text","text":"hello bot"}}""";

	@Autowired
	private MockMvc mvc;

	@Autowired
	private ViberProperties props;

	@MockitoBean
	private ViberClient viber;

	@Test
	void getReturnsStatus() throws Exception {
		mvc.perform(get("/"))
				.andExpect(status().isOk())
				.andExpect(content().string("Viber bot is running"));
	}

	@Test
	void textMessageIsAnsweredWithConfiguredReply() throws Exception {
		when(viber.sendText(anyString(), anyString())).thenReturn("{\"status\":0}");

		mvc.perform(signedPost(MESSAGE_EVENT, sign(MESSAGE_EVENT)))
				.andExpect(status().isOk());

		verify(viber).sendText("user-1", props.replyText());
	}

	@Test
	void invalidSignatureIsRejected() throws Exception {
		mvc.perform(signedPost(MESSAGE_EVENT, "deadbeef"))
				.andExpect(status().isForbidden());

		verify(viber, never()).sendText(any(), any());
	}

	@Test
	void missingSignatureIsRejected() throws Exception {
		mvc.perform(post("/").contentType(MediaType.APPLICATION_JSON).content(MESSAGE_EVENT))
				.andExpect(status().isForbidden());

		verify(viber, never()).sendText(any(), any());
	}

	@Test
	void nonMessageEventDoesNotReply() throws Exception {
		String webhookEvent = "{\"event\":\"webhook\",\"timestamp\":1,\"message_token\":2}";

		mvc.perform(signedPost(webhookEvent, sign(webhookEvent)))
				.andExpect(status().isOk());

		verify(viber, never()).sendText(any(), any());
	}

	@Test
	void failedReplyStillAcknowledgesViber() throws Exception {
		when(viber.sendText(anyString(), anyString())).thenThrow(new RuntimeException("network down"));

		mvc.perform(signedPost(MESSAGE_EVENT, sign(MESSAGE_EVENT)))
				.andExpect(status().isOk());
	}

	private static org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder signedPost(
			String body, String signature) {
		return post("/")
				.contentType(MediaType.APPLICATION_JSON)
				.header("X-Viber-Content-Signature", signature)
				.content(body);
	}

	private static String sign(String body) throws Exception {
		Mac mac = Mac.getInstance("HmacSHA256");
		mac.init(new SecretKeySpec(TOKEN.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
		return HexFormat.of().formatHex(mac.doFinal(body.getBytes(StandardCharsets.UTF_8)));
	}

}
