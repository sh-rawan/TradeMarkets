package com.trademarkets.broker.zerodha;

import static org.mockito.Mockito.doReturn;

/** Lets app tests stub KiteClient's package-private token exchange. */
public final class KiteTestAccess {

	private KiteTestAccess() {
	}

	public static void stubSession(KiteClient spy, String apiKey, String apiSecret, String requestToken,
			String userId, String accessToken) {
		doReturn(new KiteJson.Session(userId, "Test User", accessToken)).when(spy)
				.createSession(apiKey, apiSecret, requestToken);
	}

}
