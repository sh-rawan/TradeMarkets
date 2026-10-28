package com.trademarkets.broker.common.data;

import java.time.Instant;
import java.util.List;

import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import com.trademarkets.broker.common.account.BrokerAccount;
import com.trademarkets.broker.common.broker.Broker;

/** Writes sync results to the DB, each sync in one transaction. */
@Component
public class SnapshotStore {

	private final FundsRepository funds;
	private final HoldingRepository holdings;
	private final PositionRepository positions;
	private final OrderRepository orders;

	SnapshotStore(FundsRepository funds, HoldingRepository holdings, PositionRepository positions,
			OrderRepository orders) {
		this.funds = funds;
		this.holdings = holdings;
		this.positions = positions;
		this.orders = orders;
	}

	@Transactional
	public void save(BrokerAccount account, Instant takenAt, List<Broker.Funds> f, List<Broker.Holding> h,
			List<Broker.Position> p, List<Broker.Order> o) {
		funds.saveAll(f.stream().map(x -> FundsSnapshot.of(account, takenAt, x)).toList());
		holdings.saveAll(h.stream().map(x -> HoldingSnapshot.of(account, takenAt, x)).toList());
		positions.saveAll(p.stream().map(x -> PositionSnapshot.of(account, takenAt, x)).toList());
		for (Broker.Order order : o) {
			OrderRecord record = orders.findByAccountAndOrderId(account, order.orderId())
					.orElseGet(() -> new OrderRecord(account, order.orderId()));
			record.update(order);
			orders.save(record);
		}
	}

	@Transactional
	public void recordPlacedOrder(BrokerAccount account, String orderId, Broker.OrderRequest request, Instant now) {
		if (orders.findByAccountAndOrderId(account, orderId).isEmpty()) {
			orders.save(OrderRecord.placed(account, orderId, request, now));
		}
	}

	/** Deletes funds/holding/position snapshots older than cutoff. Orders are kept. */
	@Transactional
	public int deleteOlderThan(Instant cutoff) {
		return funds.deleteOlderThan(cutoff) + holdings.deleteOlderThan(cutoff) + positions.deleteOlderThan(cutoff);
	}

}
