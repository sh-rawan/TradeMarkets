package com.trademarkets.broker.zerodha;

import java.math.BigDecimal;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Stream;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.util.UriComponentsBuilder;

import com.trademarkets.broker.common.broker.AccountConfig;
import com.trademarkets.broker.common.broker.Broker;
import com.trademarkets.broker.common.broker.BrokerException;

import tools.jackson.core.JacksonException;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** Zerodha via the Kite Connect v3 REST API: https://kite.trade/docs/connect/v3/ */
@Component
public class KiteClient implements Broker {

	private static final Logger log = LoggerFactory.getLogger("broker.api");

	private static final DateTimeFormatter KITE_TIME = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

	private final KiteProperties props;
	private final RestClient rest;
	private final ObjectMapper json;

	@Autowired
	public KiteClient(KiteProperties props, ObjectMapper json) {
		this(props, json, RestClient.builder());
	}

	/** Allows tests to pass a builder bound to a mock server. */
	KiteClient(KiteProperties props, ObjectMapper json, RestClient.Builder builder) {
		this.props = props;
		this.json = json;
		this.rest = builder.baseUrl(props.apiUrl()).defaultHeader("X-Kite-Version", "3").build();
	}

	@Override
	public String name() {
		return "ZERODHA";
	}

	@Override
	public boolean supportsBrowserLogin() {
		return true;
	}

	/** Zerodha logs in through the browser once a day; Kite then redirects to KiteLoginController. */
	@Override
	public URI loginUrl(String account, AccountConfig config) {
		if (config.apiKey() == null || config.apiKey().isBlank()) {
			throw new IllegalArgumentException("Set accounts." + account + ".api-key in accounts.properties");
		}
		return UriComponentsBuilder.fromUriString(props.loginUrl())
				.queryParam("v", "3")
				.queryParam("api_key", config.apiKey())
				.queryParam("redirect_params", "account=" + account) // Kite sends this back to the callback
				.encode().build().toUri();
	}

	// ---- token exchange (used by KiteLoginController) ----

	/** Exchanges the request_token from the login redirect for an access token. */
	KiteJson.Session createSession(String apiKey, String apiSecret, String requestToken) {
		MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
		form.add("api_key", apiKey);
		form.add("request_token", requestToken);
		form.add("checksum", checksum(apiKey, requestToken, apiSecret));
		KiteJson.Session session = call("create session", rest.post().uri("/session/token")
				.contentType(MediaType.APPLICATION_FORM_URLENCODED).body(form), new TypeReference<>() {
				});
		log.info("Kite session created for user {}", session.userId());
		return session;
	}

	/** checksum = SHA-256(api_key + request_token + api_secret), hex encoded. */
	static String checksum(String apiKey, String requestToken, String apiSecret) {
		try {
			byte[] hash = MessageDigest.getInstance("SHA-256")
					.digest((apiKey + requestToken + apiSecret).getBytes(StandardCharsets.UTF_8));
			return HexFormat.of().formatHex(hash);
		}
		catch (NoSuchAlgorithmException e) {
			throw new IllegalStateException(e);
		}
	}

	// ---- read ----

	@Override
	public Profile profile(Session s) {
		KiteJson.Profile p = call("profile", get(s, "/user/profile"), new TypeReference<>() {
		});
		return new Profile(p.userId(), p.userName(), p.email(), p.exchanges());
	}

	@Override
	public List<Funds> funds(Session s) {
		KiteJson.Margins m = call("funds", get(s, "/user/margins"), new TypeReference<>() {
		});
		return Stream.of(segment("equity", m.equity()), segment("commodity", m.commodity()))
				.filter(Objects::nonNull).toList();
	}

	@Override
	public List<Holding> holdings(Session s) {
		List<KiteJson.Holding> list = call("holdings", get(s, "/portfolio/holdings"), new TypeReference<>() {
		});
		// quantity excludes shares bought in the last day (t1_quantity) - we count both as held.
		return list.stream().map(h -> new Holding(h.tradingsymbol(), h.exchange(), h.isin(),
				n(h.quantity()) + n(h.t1Quantity()), h.averagePrice(), h.lastPrice(), h.closePrice(), h.pnl(),
				h.dayChangePercentage())).toList();
	}

	/** Net positions (what is open now, including carried-forward F&amp;O). */
	@Override
	public List<Position> positions(Session s) {
		KiteJson.Positions p = call("positions", get(s, "/portfolio/positions"), new TypeReference<>() {
		});
		List<KiteJson.Position> net = p.net() == null ? List.of() : p.net();
		return net.stream().map(x -> new Position(x.tradingsymbol(), x.exchange(), x.product(), n(x.quantity()),
				x.averagePrice(), x.lastPrice(), x.pnl())).toList();
	}

	@Override
	public List<Order> orders(Session s) {
		List<KiteJson.Order> list = call("orders", get(s, "/orders"), new TypeReference<>() {
		});
		return list.stream().map(this::order).toList();
	}

	@Override
	public List<Trade> trades(Session s) {
		List<KiteJson.Trade> list = call("trades", get(s, "/trades"), new TypeReference<>() {
		});
		return list.stream().map(t -> new Trade(t.tradeId(), t.orderId(), t.tradingsymbol(), t.exchange(),
				t.transactionType(), n(t.quantity()), t.averagePrice(), time(t.fillTimestamp()))).toList();
	}

	/** Needs a Kite Connect plan with market data. */
	@Override
	public Map<String, Quote> quotes(Session s, List<String> instruments) {
		Map<String, KiteJson.Quote> raw = call("quotes", rest.get()
				.uri(b -> b.path("/quote").queryParam("i", instruments.toArray()).build())
				.header("Authorization", auth(s)), new TypeReference<>() {
				});
		Map<String, Quote> quotes = new LinkedHashMap<>();
		raw.forEach((instrument, q) -> {
			KiteJson.Ohlc o = q.ohlc() == null ? new KiteJson.Ohlc(null, null, null, null) : q.ohlc();
			quotes.put(instrument, new Quote(q.lastPrice(), o.open(), o.high(), o.low(), o.close(), n(q.volume())));
		});
		return quotes;
	}

	// ---- orders (never retried) ----

	@Override
	public String placeOrder(Session s, OrderRequest r) {
		MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
		form.add("tradingsymbol", r.symbol().toUpperCase());
		form.add("exchange", r.exchange().toUpperCase());
		form.add("transaction_type", r.side().name());
		form.add("order_type", orderType(r.type()));
		form.add("quantity", String.valueOf(r.quantity()));
		form.add("product", r.product().toUpperCase());
		form.add("validity", r.validity() == null || r.validity().isBlank() ? "DAY" : r.validity().toUpperCase());
		addIfSet(form, "price", r.price());
		addIfSet(form, "trigger_price", r.triggerPrice());
		if (r.tag() != null && !r.tag().isBlank()) {
			form.add("tag", r.tag());
		}
		String variety = r.isAfterMarket() ? "amo" : "regular";
		KiteJson.OrderId id = call("place order", rest.post().uri("/orders/{variety}", variety)
				.header("Authorization", auth(s)).contentType(MediaType.APPLICATION_FORM_URLENCODED).body(form),
				new TypeReference<>() {
				});
		return id.orderId();
	}

	@Override
	public String modifyOrder(Session s, String orderId, ModifyRequest m) {
		MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
		if (m.type() != null) {
			form.add("order_type", orderType(m.type()));
		}
		if (m.quantity() != null) {
			form.add("quantity", String.valueOf(m.quantity()));
		}
		addIfSet(form, "price", m.price());
		addIfSet(form, "trigger_price", m.triggerPrice());
		KiteJson.OrderId id = call("modify order", rest.put().uri("/orders/{variety}/{id}", variety(s, orderId), orderId)
				.header("Authorization", auth(s)).contentType(MediaType.APPLICATION_FORM_URLENCODED).body(form),
				new TypeReference<>() {
				});
		return id.orderId();
	}

	@Override
	public String cancelOrder(Session s, String orderId) {
		KiteJson.OrderId id = call("cancel order", rest.delete().uri("/orders/{variety}/{id}", variety(s, orderId), orderId)
				.header("Authorization", auth(s)), new TypeReference<>() {
				});
		return id.orderId();
	}

	/** Modify/cancel URLs need the order's variety (regular, amo, ...), so look it up from its history. */
	private String variety(Session s, String orderId) {
		List<KiteJson.Order> history = call("order history", get(s, "/orders/{id}", orderId), new TypeReference<>() {
		});
		if (history.isEmpty()) {
			throw new BrokerException("Order " + orderId + " not found", false);
		}
		String variety = history.getLast().variety();
		return variety == null ? "regular" : variety;
	}

	// ---- helpers ----

	private RestClient.RequestHeadersSpec<?> get(Session s, String path, Object... vars) {
		return rest.get().uri(path, vars).header("Authorization", auth(s));
	}

	private static String auth(Session s) {
		return "token " + s.apiKey() + ":" + s.accessToken();
	}

	/** Reads Kite's {status, data} envelope; errors become BrokerException (TokenException = login expired). */
	private <T> T call(String what, RestClient.RequestHeadersSpec<?> request, TypeReference<KiteJson.Envelope<T>> type) {
		KiteJson.Envelope<T> envelope;
		try {
			envelope = request.exchange((req, res) -> json.readValue(res.getBody(), type));
		}
		catch (RestClientException | JacksonException e) {
			log.warn("Kite {} failed: {}", what, e.getMessage());
			throw new BrokerException("Could not reach Kite: " + e.getMessage(), e);
		}
		if (envelope == null || !"success".equals(envelope.status())) {
			String message = envelope == null ? "empty response" : envelope.message();
			String errorType = envelope == null ? null : envelope.errorType();
			log.warn("Kite {} error ({}): {}", what, errorType, message);
			throw new BrokerException("Kite: " + message, "TokenException".equals(errorType));
		}
		log.debug("Kite {} ok", what);
		return envelope.data();
	}

	private Order order(KiteJson.Order o) {
		return new Order(o.orderId(), o.tradingsymbol(), o.exchange(), o.transactionType(), o.orderType(),
				o.product(), n(o.quantity()), o.price(), o.triggerPrice(), o.status(), n(o.filledQuantity()),
				o.averagePrice(), o.statusMessage(), o.tag(), time(o.orderTimestamp()),
				time(o.exchangeUpdateTimestamp()));
	}

	private static Funds segment(String name, KiteJson.Segment s) {
		if (s == null || Boolean.FALSE.equals(s.enabled())) {
			return null;
		}
		BigDecimal cash = s.available() == null ? null : s.available().cash();
		BigDecimal used = s.utilised() == null ? null : s.utilised().debits();
		return new Funds(name, cash, used, s.net());
	}

	private static String orderType(OrderType type) {
		return type == OrderType.SL_M ? "SL-M" : type.name();
	}

	private static void addIfSet(MultiValueMap<String, String> form, String key, BigDecimal value) {
		if (value != null) {
			form.add(key, value.toPlainString());
		}
	}

	/** Kite timestamps are "yyyy-MM-dd HH:mm:ss" in IST. */
	private Instant time(String value) {
		if (value == null || value.isBlank()) {
			return null;
		}
		try {
			return LocalDateTime.parse(value, KITE_TIME).atZone(props.zone()).toInstant();
		}
		catch (DateTimeParseException e) {
			return null;
		}
	}

	private static long n(Long value) {
		return value == null ? 0 : value;
	}

}
