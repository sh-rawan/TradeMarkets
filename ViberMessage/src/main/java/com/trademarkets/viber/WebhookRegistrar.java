package com.trademarkets.viber;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

/**
 * Registers the webhook with Viber once the server is up
 * (Viber verifies it by calling back immediately).
 */
@Component
public class WebhookRegistrar {

	private static final Logger log = LoggerFactory.getLogger("viber.events");

	private final ViberClient viber;
	private final ViberProperties props;

	public WebhookRegistrar(ViberClient viber, ViberProperties props) {
		this.viber = viber;
		this.props = props;
	}

	@EventListener(ApplicationReadyEvent.class)
	public void register() {
		if (props.authToken() == null || props.authToken().isBlank()) {
			log.warn("viber.auth-token is not set - add it to secrets.properties");
		}
		String url = props.webhookUrl();
		if (url == null || url.isBlank()) {
			log.info("viber.webhook-url not set - skipping webhook registration.");
			return;
		}
		log.info("Registering webhook: {}", url);
		try {
			log.info("set_webhook response: {}", viber.setWebhook(url));
		}
		catch (Exception e) {
			log.error("Webhook registration failed: {}", e.toString());
		}
	}

}
