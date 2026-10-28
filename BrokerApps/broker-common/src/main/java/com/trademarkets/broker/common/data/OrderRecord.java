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

/** A broker order. Inserted when placed through this app or first seen in a sync, then kept up to date. */
@SuppressWarnings("unused") // columns are written by JPA and read with SQL, not from Java
@Entity
@Table(name = "broker_order")
public class OrderRecord {

	@Id
	@GeneratedValue(strategy = GenerationType.IDENTITY)
	private Long id;

	@ManyToOne(fetch = FetchType.LAZY, optional = false)
	private BrokerAccount account;

	private String orderId;

	private String symbol;

	private String exchange;

	private String side;

	private String orderType;

	private String product;

	private Long quantity;

	private BigDecimal price;

	private BigDecimal triggerPrice;

	private String status;

	private Long filledQuantity;

	private BigDecimal averagePrice;

	private String statusMessage;

	private String tag;

	private Instant placedAt;

	private Instant updatedAt;

	private boolean placedByApp;

	protected OrderRecord() {
	}

	OrderRecord(BrokerAccount account, String orderId) {
		this.account = account;
		this.orderId = orderId;
	}

	/** Recorded right after this app placed it; the next sync fills in status and fills. */
	static OrderRecord placed(BrokerAccount account, String orderId, Broker.OrderRequest r, Instant now) {
		OrderRecord o = new OrderRecord(account, orderId);
		o.symbol = r.symbol();
		o.exchange = r.exchange();
		o.side = r.side().name();
		o.orderType = r.type().name();
		o.product = r.product();
		o.quantity = r.quantity();
		o.price = r.price();
		o.triggerPrice = r.triggerPrice();
		o.status = "SUBMITTED";
		o.filledQuantity = 0L;
		o.tag = r.tag();
		o.placedAt = now;
		o.updatedAt = now;
		o.placedByApp = true;
		return o;
	}

	void update(Broker.Order o) {
		symbol = o.symbol();
		exchange = o.exchange();
		side = o.side();
		orderType = o.orderType();
		product = o.product();
		quantity = o.quantity();
		price = o.price();
		triggerPrice = o.triggerPrice();
		status = o.status();
		filledQuantity = o.filledQuantity();
		averagePrice = o.averagePrice();
		statusMessage = o.statusMessage() != null && o.statusMessage().length() > 500
				? o.statusMessage().substring(0, 500) : o.statusMessage();
		tag = o.tag();
		if (o.placedAt() != null) {
			placedAt = o.placedAt();
		}
		updatedAt = o.updatedAt() != null ? o.updatedAt() : updatedAt;
	}

	public String getOrderId() {
		return orderId;
	}

	public String getStatus() {
		return status;
	}

	public Long getFilledQuantity() {
		return filledQuantity;
	}

	public boolean isPlacedByApp() {
		return placedByApp;
	}

}
