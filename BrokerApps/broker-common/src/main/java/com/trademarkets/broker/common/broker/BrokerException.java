package com.trademarkets.broker.common.broker;

/** A broker call failed. sessionExpired means the account has to log in again. */
public class BrokerException extends RuntimeException {

	private final boolean sessionExpired;

	public BrokerException(String message, boolean sessionExpired) {
		super(message);
		this.sessionExpired = sessionExpired;
	}

	public BrokerException(String message, Throwable cause) {
		super(message, cause);
		this.sessionExpired = false;
	}

	public boolean isSessionExpired() {
		return sessionExpired;
	}

}
