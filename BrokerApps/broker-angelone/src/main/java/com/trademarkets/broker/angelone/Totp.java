package com.trademarkets.broker.angelone;

import java.nio.ByteBuffer;
import java.security.GeneralSecurityException;
import java.time.Instant;
import java.util.Locale;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

/** 6-digit TOTP codes (RFC 6238: HMAC-SHA1, 30 s steps) from a base32 secret, like an authenticator app. */
final class Totp {

	private static final String BASE32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

	private Totp() {
	}

	static String code(String base32Secret, Instant now) {
		return code(base32Secret, now, 6);
	}

	static String code(String base32Secret, Instant now, int digits) {
		try {
			Mac mac = Mac.getInstance("HmacSHA1");
			mac.init(new SecretKeySpec(decodeBase32(base32Secret), "HmacSHA1"));
			byte[] hash = mac.doFinal(ByteBuffer.allocate(8).putLong(now.getEpochSecond() / 30).array());
			int offset = hash[hash.length - 1] & 0x0f;
			int binary = ((hash[offset] & 0x7f) << 24) | ((hash[offset + 1] & 0xff) << 16)
					| ((hash[offset + 2] & 0xff) << 8) | (hash[offset + 3] & 0xff);
			int otp = binary % (int) Math.pow(10, digits);
			return String.format("%0" + digits + "d", otp);
		}
		catch (GeneralSecurityException e) {
			throw new IllegalStateException(e);
		}
	}

	static byte[] decodeBase32(String secret) {
		String s = secret.replace(" ", "").replace("=", "").toUpperCase(Locale.ROOT);
		ByteBuffer out = ByteBuffer.allocate(s.length() * 5 / 8);
		int buffer = 0;
		int bits = 0;
		for (char c : s.toCharArray()) {
			int value = BASE32.indexOf(c);
			if (value < 0) {
				throw new IllegalArgumentException("totp-secret is not base32 (A-Z, 2-7)");
			}
			buffer = (buffer << 5) | value;
			bits += 5;
			if (bits >= 8) {
				out.put((byte) (buffer >> (bits - 8)));
				bits -= 8;
			}
		}
		return out.array();
	}

}
