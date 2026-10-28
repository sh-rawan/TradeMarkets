package com.trademarkets.broker.common.account;

import java.time.Clock;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.function.BiFunction;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;

import com.trademarkets.broker.common.broker.AccountConfig;
import com.trademarkets.broker.common.broker.Broker;
import com.trademarkets.broker.common.broker.Broker.Login;
import com.trademarkets.broker.common.broker.Broker.Session;
import com.trademarkets.broker.common.broker.BrokerException;
import com.trademarkets.broker.common.web.NotFoundException;

/**
 * All accounts, of any broker, come from accounts.properties (accounts.&lt;name&gt;.broker=ZERODHA, ...).
 * Their login/sync state is kept in broker_account.
 * Every broker call goes through {@link #call}: it picks the account's broker, logs in automatically where the
 * broker allows it, and notices expired logins in one place.
 */
@Service
public class AccountService {

	private static final Logger log = LoggerFactory.getLogger("broker.api");

	/** login: AUTOMATIC (e.g. TOTP), BROWSER (open loginUrl daily), TOKEN (access-token in config) or NONE. */
	public record AccountView(String name, String broker, boolean enabled, String login, boolean loggedIn,
			String userId, String userName, Instant tokenExpiresAt, Instant lastSyncAt, Boolean lastSyncOk,
			String lastSyncMessage) {
	}

	private final Map<String, Broker> brokers = new LinkedHashMap<>();
	private final Map<String, AccountConfig> configs;
	private final AccountRepository repo;
	private final Clock clock;

	public AccountService(List<Broker> brokers, Environment env, AccountRepository repo, Clock clock) {
		brokers.forEach(b -> this.brokers.put(b.name().toUpperCase(Locale.ROOT), b));
		this.configs = Binder.get(env).bind("accounts", Bindable.mapOf(String.class, AccountConfig.class))
				.orElseGet(Map::of);
		this.repo = repo;
		this.clock = clock;
		configs.forEach((name, config) -> {
			if (config.broker() == null || !this.brokers.containsKey(config.broker().toUpperCase(Locale.ROOT))) {
				throw new IllegalStateException("accounts." + name + ".broker is '" + config.broker()
						+ "' - use one of " + brokerNames());
			}
		});
	}

	public List<String> brokerNames() {
		return List.copyOf(brokers.keySet());
	}

	/** Enabled accounts, in the order of accounts.properties. */
	public List<String> names() {
		return configs.entrySet().stream().filter(e -> e.getValue().isEnabled()).map(Map.Entry::getKey).toList();
	}

	/** All accounts, including disabled ones. */
	public List<AccountView> list() {
		return configs.keySet().stream().map(this::view).toList();
	}

	public AccountView view(String name) {
		AccountConfig config = config(name);
		Broker broker = broker(name);
		BrokerAccount a = account(name);
		String login = hasText(config.accessToken()) ? "TOKEN"
				: broker.supportsAutoLogin() ? "AUTOMATIC"
				: broker.supportsBrowserLogin() ? "BROWSER" : "NONE";
		boolean loggedIn = a.hasValidToken(clock.instant()) || hasText(config.accessToken());
		return new AccountView(name, broker.name(), config.isEnabled(), login, loggedIn, a.getUserId(),
				a.getUserName(), a.getTokenExpiresAt(), a.getLastSyncAt(), a.getLastSyncOk(), a.getLastSyncMessage());
	}

	/** The account's settings from accounts.properties. */
	public AccountConfig config(String name) {
		AccountConfig config = configs.get(name);
		if (config == null) {
			throw new NotFoundException("No account '" + name + "'. Accounts: " + configs.keySet());
		}
		return config;
	}

	public Broker broker(String name) {
		return brokers.get(config(name).broker().toUpperCase(Locale.ROOT));
	}

	/** The account's DB row, created on first use. */
	public BrokerAccount account(String name) {
		String broker = broker(name).name();
		return repo.findByBrokerAndName(broker, name).orElseGet(() -> repo.save(new BrokerAccount(broker, name)));
	}

	/** Runs a broker call for the account, e.g. accounts.call("acc1", Broker::holdings). */
	public <T> T call(String name, BiFunction<Broker, Session, T> action) {
		Broker broker = broker(name);
		Session session = session(name, broker);
		try {
			return action.apply(broker, session);
		}
		catch (BrokerException e) {
			if (!e.isSessionExpired()) {
				throw e;
			}
			logout(name);
			if (!broker.supportsAutoLogin()) {
				throw e;
			}
			// The broker refused the call before acting on it, so one retry after a fresh login is safe.
			return action.apply(broker, autoLogin(name, broker));
		}
	}

	/** Logs in now, for brokers with automatic login. */
	public AccountView login(String name) {
		Broker broker = broker(name);
		if (!broker.supportsAutoLogin()) {
			throw new IllegalArgumentException(broker.name() + " has no automatic login");
		}
		autoLogin(name, broker);
		return view(name);
	}

	public void saveLogin(String name, Login login) {
		BrokerAccount a = account(name);
		a.login(login.userId(), login.userName(), login.accessToken(), login.expiresAt());
		repo.save(a);
	}

	public void logout(String name) {
		BrokerAccount a = account(name);
		a.logout();
		repo.save(a);
	}

	public void recordSync(String name, boolean ok, String message) {
		BrokerAccount a = account(name);
		a.recordSync(clock.instant(), ok, message);
		repo.save(a);
	}

	private Session session(String name, Broker broker) {
		AccountConfig config = config(name);
		if (!config.isEnabled()) {
			throw new IllegalArgumentException("Account '" + name + "' is disabled in accounts.properties");
		}
		BrokerAccount a = account(name);
		if (a.hasValidToken(clock.instant())) {
			return new Session(name, config.apiKey(), a.getAccessToken());
		}
		if (hasText(config.accessToken())) {
			return new Session(name, config.apiKey(), config.accessToken());
		}
		if (broker.supportsAutoLogin()) {
			return autoLogin(name, broker);
		}
		throw new BrokerException("Account '" + name + "' is not logged in. Open /api/accounts/" + name
				+ "/login in your browser.", true);
	}

	private Session autoLogin(String name, Broker broker) {
		AccountConfig config = config(name);
		Login login = broker.autoLogin(name, config);
		saveLogin(name, login);
		log.info("Account {} logged in automatically as {}", name, login.userId());
		return new Session(name, config.apiKey(), login.accessToken());
	}

	private static boolean hasText(String s) {
		return s != null && !s.isBlank();
	}

}
