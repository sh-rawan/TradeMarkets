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
@Table(name = "funds_snapshot")
public class FundsSnapshot {

	@Id
	@GeneratedValue(strategy = GenerationType.IDENTITY)
	private Long id;

	@ManyToOne(fetch = FetchType.LAZY, optional = false)
	private BrokerAccount account;

	private Instant takenAt;

	private String segment;

	private BigDecimal availableCash;

	private BigDecimal usedMargin;

	private BigDecimal net;

	protected FundsSnapshot() {
	}

	static FundsSnapshot of(BrokerAccount account, Instant takenAt, Broker.Funds f) {
		FundsSnapshot s = new FundsSnapshot();
		s.account = account;
		s.takenAt = takenAt;
		s.segment = f.segment();
		s.availableCash = f.availableCash();
		s.usedMargin = f.usedMargin();
		s.net = f.net();
		return s;
	}

	public Instant getTakenAt() {
		return takenAt;
	}

	public String getSegment() {
		return segment;
	}

	public BigDecimal getAvailableCash() {
		return availableCash;
	}

}
