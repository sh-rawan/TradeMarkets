package com.trademarkets.broker.common.account;

import java.time.Instant;

import com.trademarkets.broker.common.config.EncryptedStringConverter;

import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/** Login and sync state of one configured account. API keys stay in secrets.properties, not here. */
@Entity
@Table(name = "broker_account")
public class BrokerAccount {

	@Id
	@GeneratedValue(strategy = GenerationType.IDENTITY)
	private Long id;

	@Column(nullable = false)
	private String broker;

	@Column(nullable = false)
	private String name;

	private String userId;

	private String userName;

	@Convert(converter = EncryptedStringConverter.class)
	private String accessToken;

	private Instant tokenExpiresAt;

	private Instant lastSyncAt;

	private Boolean lastSyncOk;

	private String lastSyncMessage;

	protected BrokerAccount() {
	}

	public BrokerAccount(String broker, String name) {
		this.broker = broker;
		this.name = name;
	}

	public boolean hasValidToken(Instant now) {
		return accessToken != null && (tokenExpiresAt == null || now.isBefore(tokenExpiresAt));
	}

	public void login(String userId, String userName, String accessToken, Instant expiresAt) {
		this.userId = userId;
		this.userName = userName;
		this.accessToken = accessToken;
		this.tokenExpiresAt = expiresAt;
	}

	public void logout() {
		this.accessToken = null;
		this.tokenExpiresAt = null;
	}

	public void recordSync(Instant at, boolean ok, String message) {
		this.lastSyncAt = at;
		this.lastSyncOk = ok;
		this.lastSyncMessage = message != null && message.length() > 1000 ? message.substring(0, 1000) : message;
	}

	public Long getId() {
		return id;
	}

	public String getBroker() {
		return broker;
	}

	public String getName() {
		return name;
	}

	public String getUserId() {
		return userId;
	}

	public String getUserName() {
		return userName;
	}

	public String getAccessToken() {
		return accessToken;
	}

	public Instant getTokenExpiresAt() {
		return tokenExpiresAt;
	}

	public Instant getLastSyncAt() {
		return lastSyncAt;
	}

	public Boolean getLastSyncOk() {
		return lastSyncOk;
	}

	public String getLastSyncMessage() {
		return lastSyncMessage;
	}

}
