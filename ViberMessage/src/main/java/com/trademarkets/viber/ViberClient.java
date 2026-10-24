package com.trademarkets.viber;

import java.util.List;
import java.util.Map;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/** Calls the Viber REST Bot API. */
@Component
public class ViberClient {

	private final RestClient rest;
	private final ViberProperties props;

	@Autowired
	public ViberClient(ViberProperties props) {
		this(props, RestClient.builder());
	}

	/** Allows tests to pass a builder bound to a mock server. */
	ViberClient(ViberProperties props, RestClient.Builder builder) {
		this.props = props;
		this.rest = builder
				.baseUrl(props.apiUrl())
				.defaultHeader("X-Viber-Auth-Token", props.authToken())
				.build();
	}

	/** Sends a text message to a Viber user id. Returns Viber's JSON response. */
	public String sendText(String receiverId, String text) {
		return post("send_message", Map.of(
				"receiver", receiverId,
				"min_api_version", 1,
				"sender", Map.of("name", props.botName()),
				"type", "text",
				"text", text));
	}

	public String setWebhook(String url) {
		return post("set_webhook", Map.of(
				"url", url,
				"event_types", List.of("delivered", "seen", "failed", "subscribed", "unsubscribed",
						"conversation_started"),
				"send_name", true,
				"send_photo", false));
	}

	private String post(String endpoint, Map<String, ?> body) {
		return rest.post()
				.uri(endpoint)
				.contentType(MediaType.APPLICATION_JSON)
				.body(body)
				.retrieve()
				.body(String.class);
	}

}
