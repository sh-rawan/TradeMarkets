package com.trademarkets.viber;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Map;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** Receives Viber callbacks: logs incoming messages and replies with viber.reply-text. */
@RestController
public class ViberWebhookController {

	private static final Logger log = LoggerFactory.getLogger(ViberWebhookController.class);
	private static final Logger messageLog = LoggerFactory.getLogger("viber.messages");
	private static final Logger eventLog = LoggerFactory.getLogger("viber.events");

	private final ViberClient viber;
	private final ViberProperties props;
	private final ObjectMapper json;

	public ViberWebhookController(ViberClient viber, ViberProperties props, ObjectMapper json) {
		this.viber = viber;
		this.props = props;
		this.json = json;
	}

	@GetMapping("/")
	public String status() {
		return "Viber bot is running";
	}

	@PostMapping("/")
	public ResponseEntity<Void> callback(@RequestBody String body,
			@RequestHeader(name = "X-Viber-Content-Signature", required = false) String signature) {
		if (!isValidSignature(body, signature)) {
			log.warn("Rejected request with invalid signature");
			return ResponseEntity.status(403).build();
		}

		Map<String, Object> event = json.readValue(body, new TypeReference<Map<String, Object>>() {
		});
		String type = String.valueOf(event.get("event"));

		switch (type) {
			case "message" -> onMessage(event);
			case "conversation_started" -> {
				Map<?, ?> user = (Map<?, ?>) event.get("user");
				eventLog.info("Conversation started by {} ({})", user.get("name"), user.get("id"));
			}
			case "subscribed" -> {
				Map<?, ?> user = (Map<?, ?>) event.get("user");
				eventLog.info("Subscribed: {} ({})", user.get("name"), user.get("id"));
			}
			case "unsubscribed" -> eventLog.info("Unsubscribed: {}", event.get("user_id"));
			case "webhook" -> eventLog.info("Webhook verified by Viber");
			default -> eventLog.info("Event '{}': {}", type, body);
		}
		return ResponseEntity.ok().build();
	}

	private void onMessage(Map<String, Object> event) {
		Map<?, ?> sender = (Map<?, ?>) event.get("sender");
		Map<?, ?> message = (Map<?, ?>) event.get("message");
		String senderId = String.valueOf(sender.get("id"));
		String msgType = String.valueOf(message.get("type"));
		String text = msgType.equals("text") ? String.valueOf(message.get("text")) : "<" + msgType + ">";

		messageLog.info("Message from {} ({}): {}", sender.get("name"), senderId, text);

		try {
			String response = viber.sendText(senderId, props.replyText());
			Map<String, Object> result = json.readValue(response, new TypeReference<Map<String, Object>>() {
			});
			if (Integer.valueOf(0).equals(result.get("status"))) {
				messageLog.info("Replied '{}' to {} -> {}", props.replyText(), senderId, response);
			}
			else {
				messageLog.error("Viber rejected reply to {}: {}", senderId, response);
			}
		}
		catch (Exception e) {
			messageLog.error("Failed to send reply: {}", e.toString());
		}
	}

	/** Viber signs each callback body with HMAC-SHA256 using the auth token. */
	private boolean isValidSignature(String body, String signature) {
		if (signature == null) {
			return false;
		}
		try {
			Mac mac = Mac.getInstance("HmacSHA256");
			mac.init(new SecretKeySpec(props.authToken().getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
			String expected = HexFormat.of().formatHex(mac.doFinal(body.getBytes(StandardCharsets.UTF_8)));
			return MessageDigest.isEqual(expected.getBytes(StandardCharsets.US_ASCII),
					signature.toLowerCase().getBytes(StandardCharsets.US_ASCII));
		}
		catch (Exception e) {
			return false;
		}
	}

}
