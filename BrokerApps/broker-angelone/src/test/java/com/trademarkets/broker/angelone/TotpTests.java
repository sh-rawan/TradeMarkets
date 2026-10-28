package com.trademarkets.broker.angelone;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Instant;

import org.junit.jupiter.api.Test;

/** Test vectors from RFC 6238 (secret "12345678901234567890", SHA-1). */
class TotpTests {

	private static final String SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"; // base32 of "12345678901234567890"

	@Test
	void matchesRfcVectors() {
		assertThat(Totp.code(SECRET, Instant.ofEpochSecond(59), 8)).isEqualTo("94287082");
		assertThat(Totp.code(SECRET, Instant.ofEpochSecond(1111111109), 8)).isEqualTo("07081804");
		assertThat(Totp.code(SECRET, Instant.ofEpochSecond(1234567890), 8)).isEqualTo("89005924");
	}

	@Test
	void sixDigitsByDefault() {
		assertThat(Totp.code(SECRET, Instant.ofEpochSecond(59))).isEqualTo("287082");
	}

	@Test
	void secretMayHaveSpacesAndLowerCase() {
		assertThat(Totp.code("gezd gnbv gy3t qojq gezd gnbv gy3t qojq", Instant.ofEpochSecond(59))).isEqualTo("287082");
	}

	@Test
	void rejectsNonBase32() {
		assertThatThrownBy(() -> Totp.code("not-base32!", Instant.now())).isInstanceOf(IllegalArgumentException.class);
	}

}
