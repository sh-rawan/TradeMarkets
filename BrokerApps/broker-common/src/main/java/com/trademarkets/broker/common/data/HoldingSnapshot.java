package com.trademarkets.broker.common.data;

import java.math.BigDecimal;
import java.time.Instant;

import com.trademarkets.broker.common.account.BrokerAccount;
import com.trademarkets.broker.common.broker.Broker;

import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@SuppressWarnings("unused") // columns are written by JPA and read with SQL, not from Java
@Entity
@Table(name = "holding_snapshot")
public class HoldingSnapshot {

	@Id
	@GeneratedValue(strategy = GenerationType.IDENTITY)
	private Long id;

	@ManyToOne(fetch = FetchType.LAZY, optional = false)
	private BrokerAccount account;

	private Instant takenAt;

	private String symbol;

	private String exchange;

	private String isin;

	private long quantity;

	private BigDecimal averagePrice;

	private BigDecimal lastPrice;

	private BigDecimal closePrice;

	private BigDecimal pnl;

	private BigDecimal dayChangePct;

	protected HoldingSnapshot() {
	}

	static HoldingSnapshot of(BrokerAccount account, Instant takenAt, Broker.Holding h) {
		HoldingSnapshot s = new HoldingSnapshot();
		s.account = account;
		s.takenAt = takenAt;
		s.symbol = h.symbol();
		s.exchange = h.exchange();
		s.isin = h.isin();
		s.quantity = h.quantity();
		s.averagePrice = h.averagePrice();
		s.lastPrice = h.lastPrice();
		s.closePrice = h.closePrice();
		s.pnl = h.pnl();
		s.dayChangePct = h.dayChangePct();
		return s;
	}

	public Instant getTakenAt() {
		return takenAt;
	}

	public String getSymbol() {
		return symbol;
	}

	public long getQuantity() {
		return quantity;
	}

}
