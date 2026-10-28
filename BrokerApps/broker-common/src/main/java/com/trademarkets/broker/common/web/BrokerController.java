package com.trademarkets.broker.common.web;

import java.math.BigDecimal;
import java.net.URI;
import java.util.Arrays;
import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.trademarkets.broker.common.account.AccountService;
import com.trademarkets.broker.common.account.AccountService.AccountView;
import com.trademarkets.broker.common.broker.Broker;
import com.trademarkets.broker.common.broker.Broker.Funds;
import com.trademarkets.broker.common.broker.Broker.Holding;
import com.trademarkets.broker.common.broker.Broker.ModifyRequest;
import com.trademarkets.broker.common.broker.Broker.Order;
import com.trademarkets.broker.common.broker.Broker.OrderRequest;
import com.trademarkets.broker.common.broker.Broker.Position;
import com.trademarkets.broker.common.broker.Broker.Profile;
import com.trademarkets.broker.common.broker.Broker.Quote;
import com.trademarkets.broker.common.broker.Broker.Trade;
import com.trademarkets.broker.common.config.TradingProperties;
import com.trademarkets.broker.common.data.SyncService;
import com.trademarkets.broker.common.data.SyncService.SyncResult;
import com.trademarkets.broker.common.trading.TradingService;

import jakarta.validation.Valid;

/**
 * One REST API for every account of every broker: /api/accounts/{account}/... is routed to that account's
 * broker. Live data comes straight from the broker.
 */
@RestController
@RequestMapping("/api")
class BrokerController {

	private final AccountService accounts;
	private final SyncService sync;
	private final TradingService trading;
	private final TradingProperties tradingProps;

	BrokerController(AccountService accounts, SyncService sync, TradingService trading,
			TradingProperties tradingProps) {
		this.accounts = accounts;
		this.sync = sync;
		this.trading = trading;
		this.tradingProps = tradingProps;
	}

	record Info(List<String> brokers, List<String> accounts, boolean tradingEnabled, BigDecimal maxOrderValue) {
	}

	@GetMapping("/info")
	Info info() {
		return new Info(accounts.brokerNames(), accounts.names(), tradingProps.enabled(),
				tradingProps.hasMaxOrderValue() ? tradingProps.maxOrderValue() : null);
	}

	@GetMapping("/accounts")
	List<AccountView> accounts() {
		return accounts.list();
	}

	@GetMapping("/accounts/{account}")
	AccountView account(@PathVariable String account) {
		return accounts.view(account);
	}

	/**
	 * Logs in: automatic brokers log in right away, browser brokers (Zerodha) redirect to their login page.
	 * GET so it can be opened from a browser.
	 */
	@GetMapping("/accounts/{account}/login")
	ResponseEntity<?> login(@PathVariable String account) {
		Broker broker = accounts.broker(account);
		if (broker.supportsAutoLogin()) {
			return ResponseEntity.ok(accounts.login(account));
		}
		URI url = broker.loginUrl(account, accounts.config(account));
		if (url == null) {
			throw new IllegalArgumentException(broker.name() + " has no login. Set accounts." + account
					+ ".access-token in accounts.properties.");
		}
		return ResponseEntity.status(HttpStatus.FOUND).location(url).build();
	}

	@PostMapping("/accounts/{account}/logout")
	AccountView logout(@PathVariable String account) {
		accounts.logout(account);
		return accounts.view(account);
	}

	@GetMapping("/accounts/{account}/profile")
	Profile profile(@PathVariable String account) {
		return accounts.call(account, Broker::profile);
	}

	@GetMapping("/accounts/{account}/funds")
	List<Funds> funds(@PathVariable String account) {
		return accounts.call(account, Broker::funds);
	}

	@GetMapping("/accounts/{account}/holdings")
	List<Holding> holdings(@PathVariable String account) {
		return accounts.call(account, Broker::holdings);
	}

	@GetMapping("/accounts/{account}/positions")
	List<Position> positions(@PathVariable String account) {
		return accounts.call(account, Broker::positions);
	}

	@GetMapping("/accounts/{account}/orders")
	List<Order> orders(@PathVariable String account) {
		return accounts.call(account, Broker::orders);
	}

	@GetMapping("/accounts/{account}/trades")
	List<Trade> trades(@PathVariable String account) {
		return accounts.call(account, Broker::trades);
	}

	/** ?instruments=NSE:INFY,NSE:TCS */
	@GetMapping("/accounts/{account}/quotes")
	Map<String, Quote> quotes(@PathVariable String account, @RequestParam String instruments) {
		List<String> list = Arrays.stream(instruments.split(",")).map(String::trim).filter(s -> !s.isEmpty())
				.toList();
		return accounts.call(account, (b, s) -> b.quotes(s, list));
	}

	record OrderId(String orderId) {
	}

	@PostMapping("/accounts/{account}/orders")
	OrderId placeOrder(@PathVariable String account, @Valid @RequestBody OrderRequest request) {
		return new OrderId(trading.place(account, request));
	}

	@PutMapping("/accounts/{account}/orders/{orderId}")
	OrderId modifyOrder(@PathVariable String account, @PathVariable String orderId,
			@Valid @RequestBody ModifyRequest request) {
		return new OrderId(trading.modify(account, orderId, request));
	}

	@DeleteMapping("/accounts/{account}/orders/{orderId}")
	OrderId cancelOrder(@PathVariable String account, @PathVariable String orderId) {
		return new OrderId(trading.cancel(account, orderId));
	}

	@PostMapping("/sync")
	List<SyncResult> syncAll() {
		return sync.syncAll();
	}

	@PostMapping("/accounts/{account}/sync")
	SyncResult syncAccount(@PathVariable String account) {
		return sync.sync(account);
	}

}
