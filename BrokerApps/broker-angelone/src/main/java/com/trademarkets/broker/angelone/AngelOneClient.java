package com.trademarkets.broker.angelone;

import java.math.BigDecimal;
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import com.trademarkets.broker.common.broker.AccountConfig;
import com.trademarkets.broker.common.broker.Broker;
import com.trademarkets.broker.common.broker.BrokerException;

import tools.jackson.core.JacksonException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/**
 * Angel One via SmartAPI (https://smartapi.angelone.in/docs). Logs in automatically with client code,
 * MPIN and the TOTP secret, so no daily browser login is needed.
 * SmartAPI sends many numbers as strings, so responses are read as JSON trees.
 */
@Component
public class AngelOneClient implements Broker {

	private static final Logger log = LoggerFactory.getLogger("broker.api");

	/** SmartAPI error codes that mean "log in again". */
	private static final Set<String> TOKEN_ERRORS = Set.of("AG8001", "AG8002", "AG8003");

	private static final DateTimeFormatter ANGEL_TIME = new DateTimeFormatterBuilder().parseCaseInsensitive()
			.appendPattern("dd-MMM-yyyy HH:mm:ss").toFormatter(Locale.ENGLISH);

	private static final String API = "/rest/secure/angelbroking";

	private final AngelOneProperties props;
	private final RestClient rest;
	private final ObjectMapper json;
	private final Clock clock;

	/** "NSE:SBIN" -> Angel's symbol token and trading symbol, looked up once via searchScrip. */
	private final Map<String, Instrument> instruments = new ConcurrentHashMap<>();

	record Instrument(String exchange, String tradingSymbol, String token) {
	}

	@Autowired
	public AngelOneClient(AngelOneProperties props, ObjectMapper json, Clock clock) {
		this(props, json, clock, RestClient.builder());
	}

	/** Allows tests to pass a builder bound to a mock server. */
	AngelOneClient(AngelOneProperties props, ObjectMapper json, Clock clock, RestClient.Builder builder) {
		this.props = props;
		this.json = json;
		this.clock = clock;
		String localIp = orDefault(props.localIp(), detectLocalIp());
		this.rest = builder.baseUrl(props.apiUrl())
				.defaultHeader("Content-Type", MediaType.APPLICATION_JSON_VALUE)
				.defaultHeader("Accept", MediaType.APPLICATION_JSON_VALUE)
				.defaultHeader("X-UserType", "USER")
				.defaultHeader("X-SourceID", "WEB")
				.defaultHeader("X-ClientLocalIP", localIp)
				.defaultHeader("X-ClientPublicIP", orDefault(props.publicIp(), localIp))
				.defaultHeader("X-MACAddress", orDefault(props.macAddress(), detectMac()))
				.build();
	}

	@Override
	public String name() {
		return "ANGELONE";
	}

	// ---- login ----

	@Override
	public boolean supportsAutoLogin() {
		return true;
	}

	@Override
	public Login autoLogin(String account, AccountConfig c) {
		for (String[] field : new String[][] { { "api-key", c.apiKey() }, { "client-id", c.clientId() },
				{ "pin", c.pin() }, { "totp-secret", c.totpSecret() } }) {
			if (field[1] == null || field[1].isBlank()) {
				throw new BrokerException("Set accounts." + account + "." + field[0] + " in accounts.properties", false);
			}
		}
		String totp;
		try {
			totp = Totp.code(c.totpSecret(), clock.instant());
		}
		catch (IllegalArgumentException e) {
			throw new BrokerException("accounts." + account + ".totp-secret: " + e.getMessage(), false);
		}
		JsonNode data = call("login", rest.post().uri("/rest/auth/angelbroking/user/v1/loginByPassword")
				.header("X-PrivateKey", c.apiKey())
				.body(Map.of("clientcode", c.clientId(), "password", c.pin(), "totp", totp)));
		String token = text(data, "jwtToken");
		if (token == null) {
			throw new BrokerException("Angel One login returned no token", false);
		}
		token = token.startsWith("Bearer ") ? token.substring(7) : token;
		String userName = null;
		try {
			userName = profile(new Session(account, c.apiKey(), token)).userName();
		}
		catch (BrokerException e) {
			log.warn("Angel One profile after login failed: {}", e.getMessage());
		}
		log.info("Angel One login ok for client {}", c.clientId());
		return new Login(c.clientId(), userName, token, nextExpiry());
	}

	/** Treated as expiring at the next tokenExpiryTime; if Angel expires it earlier we just log in again. */
	Instant nextExpiry() {
		ZonedDateTime now = ZonedDateTime.now(clock.withZone(props.zone()));
		ZonedDateTime expiry = now.toLocalDate().atTime(props.tokenExpiryTime()).atZone(props.zone());
		return (now.isBefore(expiry) ? expiry : expiry.plusDays(1)).toInstant();
	}

	// ---- read ----

	@Override
	public Profile profile(Session s) {
		JsonNode d = call("profile", get(s, "/user/v1/getProfile"));
		JsonNode ex = d.path("exchanges");
		List<String> exchanges = new ArrayList<>();
		if (ex.isString()) { // sometimes a JSON array inside a string
			try {
				ex = json.readTree(ex.asString());
			}
			catch (JacksonException e) {
				ex = d.path("none");
			}
		}
		ex.values().forEach(e -> exchanges.add(e.asString()));
		return new Profile(text(d, "clientcode"), text(d, "name"), text(d, "email"), exchanges);
	}

	/** Angel reports one combined cash/margin figure, not per segment. */
	@Override
	public List<Funds> funds(Session s) {
		JsonNode d = call("funds", get(s, "/user/v1/getRMS"));
		return List.of(new Funds("all", num(d, "availablecash"), num(d, "utiliseddebits"), num(d, "net")));
	}

	@Override
	public List<Holding> holdings(Session s) {
		List<Holding> list = new ArrayList<>();
		for (JsonNode h : array(call("holdings", get(s, "/portfolio/v1/getHolding")))) {
			// quantity excludes shares bought in the last day (t1quantity) - we count both as held.
			list.add(new Holding(symbol(text(h, "tradingsymbol")), text(h, "exchange"), text(h, "isin"),
					lng(h, "quantity") + lng(h, "t1quantity"), num(h, "averageprice"), num(h, "ltp"), num(h, "close"),
					num(h, "profitandloss"), num(h, "pnlpercentage")));
		}
		return list;
	}

	@Override
	public List<Position> positions(Session s) {
		List<Position> list = new ArrayList<>();
		for (JsonNode p : array(call("positions", get(s, "/order/v1/getPosition")))) {
			BigDecimal avg = num(p, "avgnetprice") != null ? num(p, "avgnetprice") : num(p, "netprice");
			list.add(new Position(symbol(text(p, "tradingsymbol")), text(p, "exchange"),
					product(text(p, "producttype")), lng(p, "netqty"), avg, num(p, "ltp"), num(p, "pnl")));
		}
		return list;
	}

	@Override
	public List<Order> orders(Session s) {
		return array(call("orders", get(s, "/order/v1/getOrderBook"))).stream().map(this::order).toList();
	}

	@Override
	public List<Trade> trades(Session s) {
		LocalDate today = LocalDate.now(clock.withZone(props.zone()));
		List<Trade> list = new ArrayList<>();
		for (JsonNode t : array(call("trades", get(s, "/order/v1/getTradeBook")))) {
			Instant filled = null;
			try {
				filled = today.atTime(LocalTime.parse(text(t, "filltime"))).atZone(props.zone()).toInstant();
			}
			catch (DateTimeParseException | NullPointerException e) {
				// leave empty
			}
			list.add(new Trade(text(t, "fillid"), text(t, "orderid"), symbol(text(t, "tradingsymbol")),
					text(t, "exchange"), text(t, "transactiontype"), lng(t, "fillsize"), num(t, "fillprice"), filled));
		}
		return list;
	}

	@Override
	public Map<String, Quote> quotes(Session s, List<String> wanted) {
		Map<String, List<String>> tokensByExchange = new LinkedHashMap<>();
		Map<String, String> instrumentByToken = new LinkedHashMap<>();
		for (String w : wanted) {
			Instrument i = instrument(s, w);
			tokensByExchange.computeIfAbsent(i.exchange(), k -> new ArrayList<>()).add(i.token());
			instrumentByToken.put(i.exchange() + ":" + i.token(), w);
		}
		JsonNode d = call("quotes", post(s, "/market/v1/quote/",
				Map.of("mode", "FULL", "exchangeTokens", tokensByExchange)));
		Map<String, Quote> quotes = new LinkedHashMap<>();
		for (JsonNode q : array(d.path("fetched"))) {
			String key = instrumentByToken.get(text(q, "exchange") + ":" + text(q, "symbolToken"));
			if (key != null) {
				quotes.put(key, new Quote(num(q, "ltp"), num(q, "open"), num(q, "high"), num(q, "low"),
						num(q, "close"), lng(q, "tradeVolume")));
			}
		}
		return quotes;
	}

	// ---- orders (never retried) ----

	@Override
	public String placeOrder(Session s, OrderRequest r) {
		Instrument i = instrument(s, r.exchange() + ":" + r.symbol());
		boolean stopLoss = r.type() == OrderType.SL || r.type() == OrderType.SL_M;
		Map<String, Object> body = new LinkedHashMap<>();
		body.put("variety", r.isAfterMarket() ? "AMO" : stopLoss ? "STOPLOSS" : "NORMAL");
		body.put("tradingsymbol", i.tradingSymbol());
		body.put("symboltoken", i.token());
		body.put("transactiontype", r.side().name());
		body.put("exchange", i.exchange());
		body.put("ordertype", orderType(r.type()));
		body.put("producttype", angelProduct(r.product()));
		body.put("duration", r.validity() == null || r.validity().isBlank() ? "DAY" : r.validity().toUpperCase());
		body.put("price", plain(r.price()));
		body.put("triggerprice", plain(r.triggerPrice()));
		body.put("squareoff", "0");
		body.put("stoploss", "0");
		body.put("quantity", String.valueOf(r.quantity()));
		if (r.tag() != null && !r.tag().isBlank()) {
			body.put("ordertag", r.tag());
		}
		return text(call("place order", post(s, "/order/v1/placeOrder", body)), "orderid");
	}

	@Override
	public String modifyOrder(Session s, String orderId, ModifyRequest m) {
		JsonNode o = findOrder(s, orderId);
		Map<String, Object> body = new LinkedHashMap<>();
		body.put("variety", text(o, "variety"));
		body.put("orderid", orderId);
		body.put("ordertype", m.type() != null ? orderType(m.type()) : text(o, "ordertype"));
		body.put("producttype", text(o, "producttype"));
		body.put("duration", text(o, "duration"));
		body.put("price", m.price() != null ? plain(m.price()) : text(o, "price"));
		body.put("triggerprice", m.triggerPrice() != null ? plain(m.triggerPrice()) : text(o, "triggerprice"));
		body.put("quantity", m.quantity() != null ? String.valueOf(m.quantity()) : text(o, "quantity"));
		body.put("tradingsymbol", text(o, "tradingsymbol"));
		body.put("symboltoken", text(o, "symboltoken"));
		body.put("exchange", text(o, "exchange"));
		return text(call("modify order", post(s, "/order/v1/modifyOrder", body)), "orderid");
	}

	@Override
	public String cancelOrder(Session s, String orderId) {
		JsonNode o = findOrder(s, orderId);
		return text(call("cancel order", post(s, "/order/v1/cancelOrder",
				Map.of("variety", text(o, "variety"), "orderid", orderId))), "orderid");
	}

	private JsonNode findOrder(Session s, String orderId) {
		return array(call("orders", get(s, "/order/v1/getOrderBook"))).stream()
				.filter(o -> orderId.equals(text(o, "orderid")))
				.findFirst()
				.orElseThrow(() -> new BrokerException("Order " + orderId + " not found in today's order book", false));
	}

	/** Angel needs a symbol token for orders and quotes; searchScrip finds it (e.g. NSE:SBIN -> SBIN-EQ, 3045). */
	Instrument instrument(Session s, String exchangeAndSymbol) {
		String key = exchangeAndSymbol.toUpperCase(Locale.ROOT);
		Instrument cached = instruments.get(key);
		if (cached != null) {
			return cached;
		}
		int colon = key.indexOf(':');
		if (colon < 1) {
			throw new IllegalArgumentException("Instrument must be EXCHANGE:SYMBOL, e.g. NSE:SBIN");
		}
		String exchange = key.substring(0, colon);
		String symbol = key.substring(colon + 1);
		JsonNode found = call("search " + key, post(s, "/order/v1/searchScrip",
				Map.of("exchange", exchange, "searchscrip", symbol)));
		for (JsonNode f : array(found)) {
			String ts = text(f, "tradingsymbol");
			if (symbol.equalsIgnoreCase(ts) || (symbol + "-EQ").equalsIgnoreCase(ts)) {
				Instrument i = new Instrument(exchange, ts, text(f, "symboltoken"));
				instruments.put(key, i);
				return i;
			}
		}
		throw new BrokerException("Angel One has no instrument " + key, false);
	}

	// ---- HTTP ----

	private RestClient.RequestHeadersSpec<?> get(Session s, String path) {
		return rest.get().uri(API + path).headers(h -> auth(h, s));
	}

	private RestClient.RequestHeadersSpec<?> post(Session s, String path, Object body) {
		return rest.post().uri(API + path).headers(h -> auth(h, s)).body(body);
	}

	private static void auth(org.springframework.http.HttpHeaders h, Session s) {
		h.set("Authorization", "Bearer " + s.accessToken());
		h.set("X-PrivateKey", s.apiKey());
	}

	/**
	 * Reads SmartAPI's {status, message, errorcode, data} envelope and returns data.
	 * Invalid/expired token errors (AG8001-AG8003, or HTTP 401/403) become a "log in again" BrokerException.
	 */
	private JsonNode call(String what, RestClient.RequestHeadersSpec<?> request) {
		JsonNode body;
		int httpStatus;
		try {
			record Response(int status, JsonNode body) {
			}
			Response r = request.exchange((req, res) -> {
				int code = res.getStatusCode().value();
				try {
					return new Response(code, json.readTree(res.getBody()));
				}
				catch (JacksonException e) {
					return new Response(code, null);
				}
			});
			httpStatus = r.status();
			body = r.body();
		}
		catch (RestClientException e) {
			log.warn("Angel One {} failed: {}", what, e.getMessage());
			throw new BrokerException("Could not reach Angel One: " + e.getMessage(), e);
		}
		boolean authFailed = httpStatus == 401 || httpStatus == 403;
		if (body == null || body.isMissingNode() || body.isNull()) {
			log.warn("Angel One {}: HTTP {} with no JSON body", what, httpStatus);
			throw new BrokerException("Angel One " + what + " failed (HTTP " + httpStatus + ")", authFailed);
		}
		boolean ok = body.path("status").asBoolean(false) || body.path("success").asBoolean(false);
		if (!ok) {
			String code = text(body, "errorcode") != null ? text(body, "errorcode") : text(body, "errorCode");
			String message = text(body, "message");
			log.warn("Angel One {} error ({}): {}", what, code, message);
			throw new BrokerException("Angel One: " + message + (code == null ? "" : " (" + code + ")"),
					authFailed || (code != null && TOKEN_ERRORS.contains(code)));
		}
		log.debug("Angel One {} ok", what);
		return body.path("data");
	}

	// ---- mapping ----

	private Order order(JsonNode o) {
		String status = text(o, "orderstatus") != null ? text(o, "orderstatus") : text(o, "status");
		Instant updated = time(text(o, "exchorderupdatetime")) != null ? time(text(o, "exchorderupdatetime"))
				: time(text(o, "updatetime"));
		return new Order(text(o, "orderid"), symbol(text(o, "tradingsymbol")), text(o, "exchange"),
				text(o, "transactiontype"), commonOrderType(text(o, "ordertype")), product(text(o, "producttype")),
				lng(o, "quantity"), num(o, "price"), num(o, "triggerprice"),
				status == null ? null : status.toUpperCase(Locale.ROOT), lng(o, "filledshares"),
				num(o, "averageprice"), text(o, "text"), text(o, "ordertag"), time(text(o, "updatetime")), updated);
	}

	private static String orderType(OrderType type) {
		return switch (type) {
			case MARKET -> "MARKET";
			case LIMIT -> "LIMIT";
			case SL -> "STOPLOSS_LIMIT";
			case SL_M -> "STOPLOSS_MARKET";
		};
	}

	private static String commonOrderType(String angel) {
		if (angel == null) {
			return null;
		}
		return switch (angel) {
			case "STOPLOSS_LIMIT" -> "SL";
			case "STOPLOSS_MARKET" -> "SL_M";
			default -> angel;
		};
	}

	/** The API uses Zerodha's product names everywhere; Angel's own names also work. */
	private static String angelProduct(String product) {
		return switch (product.toUpperCase(Locale.ROOT)) {
			case "CNC" -> "DELIVERY";
			case "MIS" -> "INTRADAY";
			case "NRML" -> "CARRYFORWARD";
			default -> product.toUpperCase(Locale.ROOT);
		};
	}

	private static String product(String angel) {
		if (angel == null) {
			return null;
		}
		return switch (angel.toUpperCase(Locale.ROOT)) {
			case "DELIVERY" -> "CNC";
			case "INTRADAY" -> "MIS";
			case "CARRYFORWARD" -> "NRML";
			default -> angel;
		};
	}

	/** NSE equities are "SBIN-EQ" at Angel; stored as "SBIN" like other brokers. */
	private static String symbol(String angel) {
		return angel != null && angel.endsWith("-EQ") ? angel.substring(0, angel.length() - 3) : angel;
	}

	private Instant time(String value) {
		if (value == null || value.isBlank()) {
			return null;
		}
		try {
			return LocalDateTime.parse(value.trim(), ANGEL_TIME).atZone(props.zone()).toInstant();
		}
		catch (DateTimeParseException e) {
			return null;
		}
	}

	private static List<JsonNode> array(JsonNode node) {
		return node != null && node.isArray() ? List.copyOf(node.values()) : List.of();
	}

	private static String text(JsonNode node, String field) {
		JsonNode v = node.path(field);
		return v.isMissingNode() || v.isNull() ? null : v.asString();
	}

	/** Numbers come as numbers or as strings like "1,234.50" or "- 22.5". */
	private static BigDecimal num(JsonNode node, String field) {
		JsonNode v = node.path(field);
		if (v.isNumber()) {
			return v.decimalValue();
		}
		if (v.isString()) {
			String s = v.asString().replace(",", "").replace(" ", "");
			try {
				return s.isEmpty() ? null : new BigDecimal(s);
			}
			catch (NumberFormatException e) {
				return null;
			}
		}
		return null;
	}

	private static long lng(JsonNode node, String field) {
		BigDecimal n = num(node, field);
		return n == null ? 0 : n.longValue();
	}

	private static String plain(BigDecimal value) {
		return value == null ? "0" : value.toPlainString();
	}

	private static String orDefault(String value, String fallback) {
		return value == null || value.isBlank() ? fallback : value;
	}

	private static String detectLocalIp() {
		try {
			return InetAddress.getLocalHost().getHostAddress();
		}
		catch (Exception e) {
			return "127.0.0.1";
		}
	}

	private static String detectMac() {
		try {
			NetworkInterface ni = NetworkInterface.getByInetAddress(InetAddress.getLocalHost());
			if (ni != null && ni.getHardwareAddress() != null) {
				return HexFormat.ofDelimiter(":").withUpperCase().formatHex(ni.getHardwareAddress());
			}
		}
		catch (Exception e) {
			// fall through
		}
		return "00:00:00:00:00:00";
	}

}
