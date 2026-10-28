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
@Table(name = "position_snapshot")
public class PositionSnapshot {

	@Id
	@GeneratedValue(strategy = GenerationType.IDENTITY)
	private Long id;

	@ManyToOne(fetch = FetchType.LAZY, optional = false)
	private BrokerAccount account;

	private Instant takenAt;

	private String symbol;

	private String exchange;

	private String product;

	private long quantity;

	private BigDecimal averagePrice;

	private BigDecimal lastPrice;

	private BigDecimal pnl;

	protected PositionSnapshot() {
	}

	static PositionSnapshot of(BrokerAccount account, Instant takenAt, Broker.Position p) {
		PositionSnapshot s = new PositionSnapshot();
		s.account = account;
		s.takenAt = takenAt;
		s.symbol = p.symbol();
		s.exchange = p.exchange();
		s.product = p.product();
		s.quantity = p.quantity();
		s.averagePrice = p.averagePrice();
		s.lastPrice = p.lastPrice();
		s.pnl = p.pnl();
		return s;
	}

	public Instant getTakenAt() {
		return takenAt;
	}

	public String getSymbol() {
		return symbol;
	}

}
