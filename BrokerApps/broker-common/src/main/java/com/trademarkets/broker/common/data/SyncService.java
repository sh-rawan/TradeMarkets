package com.trademarkets.broker.common.data;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import com.trademarkets.broker.common.account.AccountService;
import com.trademarkets.broker.common.broker.Broker;
import com.trademarkets.broker.common.broker.BrokerException;
import com.trademarkets.broker.common.config.SyncProperties;

/** Fetches funds, holdings, positions and orders from the broker and stores them. */
@Service
public class SyncService {

	private static final Logger log = LoggerFactory.getLogger("broker.sync");

	public record SyncResult(String account, boolean ok, String message, int funds, int holdings, int positions,
			int orders) {
	}

	private final AccountService accounts;
	private final SnapshotStore store;
	private final SyncProperties props;
	private final Clock clock;

	SyncService(AccountService accounts, SnapshotStore store, SyncProperties props, Clock clock) {
		this.accounts = accounts;
		this.store = store;
		this.props = props;
		this.clock = clock;
	}

	public List<SyncResult> syncAll() {
		return accounts.names().stream().map(this::sync).toList();
	}

	/** Never throws for broker problems: the result (and the account row) says what went wrong. */
	public SyncResult sync(String name) {
		accounts.config(name); // unknown account -> 404
		Instant now = clock.instant();
		try {
			var funds = accounts.call(name, Broker::funds);
			var holdings = accounts.call(name, Broker::holdings);
			var positions = accounts.call(name, Broker::positions);
			var orders = accounts.call(name, Broker::orders);
			store.save(accounts.account(name), now, funds, holdings, positions, orders);
			String message = "%d holdings, %d positions, %d orders".formatted(holdings.size(), positions.size(),
					orders.size());
			accounts.recordSync(name, true, message);
			log.info("Synced {}: {}", name, message);
			return new SyncResult(name, true, message, funds.size(), holdings.size(), positions.size(), orders.size());
		}
		catch (RuntimeException e) {
			accounts.recordSync(name, false, e.getMessage());
			if (e instanceof BrokerException b && b.isSessionExpired()) {
				log.info("Skipped {}: {}", name, e.getMessage()); // normal until the daily login
			}
			else {
				log.warn("Sync of {} failed: {}", name, e.getMessage());
			}
			return new SyncResult(name, false, e.getMessage(), 0, 0, 0, 0);
		}
	}

	public int deleteOldSnapshots() {
		Instant cutoff = clock.instant().minus(Duration.ofDays(props.retentionDays()));
		int deleted = store.deleteOlderThan(cutoff);
		log.info("Deleted {} snapshot rows older than {} days", deleted, props.retentionDays());
		return deleted;
	}

}
