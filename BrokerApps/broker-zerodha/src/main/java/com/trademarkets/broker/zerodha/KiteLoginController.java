package com.trademarkets.broker.zerodha;

import java.time.Clock;
import java.time.Instant;
import java.time.ZonedDateTime;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.trademarkets.broker.common.account.AccountService;
import com.trademarkets.broker.common.broker.AccountConfig;
import com.trademarkets.broker.common.broker.Broker;
import com.trademarkets.broker.common.broker.BrokerException;
import com.trademarkets.broker.common.data.SyncService;
import com.trademarkets.broker.common.data.SyncService.SyncResult;

/**
 * Daily Kite login, step 2. /api/accounts/{name}/login sends the browser to Zerodha; after login Kite redirects
 * here (set http://localhost:8091/api/kite/callback as the Redirect URL of your Kite Connect app).
 */
@RestController
class KiteLoginController {

	private static final Logger log = LoggerFactory.getLogger("broker.api");

	private final KiteClient kite;
	private final KiteProperties props;
	private final AccountService accounts;
	private final SyncService sync;
	private final Clock clock;

	KiteLoginController(KiteClient kite, KiteProperties props, AccountService accounts, SyncService sync,
			Clock clock) {
		this.kite = kite;
		this.props = props;
		this.accounts = accounts;
		this.sync = sync;
		this.clock = clock;
	}

	@GetMapping(value = "/api/kite/callback", produces = MediaType.TEXT_PLAIN_VALUE)
	ResponseEntity<String> callback(@RequestParam String account,
			@RequestParam(name = "request_token", required = false) String requestToken,
			@RequestParam(required = false) String status) {
		if (!kite.name().equals(accounts.broker(account).name())) {
			return ResponseEntity.badRequest().body("Account '" + account + "' is not a Zerodha account.");
		}
		if (!"success".equals(status) || requestToken == null) {
			return ResponseEntity.badRequest().body("Zerodha login for '" + account + "' was cancelled or failed.");
		}
		AccountConfig config = accounts.config(account);
		KiteJson.Session session;
		try {
			session = kite.createSession(config.apiKey(), config.apiSecret(), requestToken);
		}
		catch (BrokerException e) {
			return ResponseEntity.status(HttpStatus.BAD_GATEWAY).body("Zerodha login failed: " + e.getMessage());
		}
		Instant expires = nextExpiry();
		accounts.saveLogin(account,
				new Broker.Login(session.userId(), session.userName(), session.accessToken(), expires));
		log.info("Account {} logged in as {}", account, session.userId());

		SyncResult first = sync.sync(account);
		return ResponseEntity.ok("""
				Zerodha account '%s' connected as %s (%s).
				Login valid until %s.
				First sync: %s
				You can close this tab.""".formatted(account, session.userId(), session.userName(),
				expires.atZone(props.zone()).toLocalDateTime(), first.message()));
	}

	/** Kite tokens expire at the next tokenExpiryTime (06:00 IST). */
	Instant nextExpiry() {
		ZonedDateTime now = ZonedDateTime.now(clock.withZone(props.zone()));
		ZonedDateTime expiry = now.toLocalDate().atTime(props.tokenExpiryTime()).atZone(props.zone());
		return (now.isBefore(expiry) ? expiry : expiry.plusDays(1)).toInstant();
	}

}
