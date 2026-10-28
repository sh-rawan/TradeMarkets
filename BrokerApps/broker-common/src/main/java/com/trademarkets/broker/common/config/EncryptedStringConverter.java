package com.trademarkets.broker.common.config;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Base64;

import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

import org.springframework.stereotype.Component;

import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

/**
 * Encrypts access tokens in the DB with AES-256-GCM.
 * Stored format: base64(iv || ciphertext). Key comes from app.encryption-key in secrets.properties.
 */
@Component
@Converter
public class EncryptedStringConverter implements AttributeConverter<String, String> {

	private static final int IV_BYTES = 12;
	private static final int TAG_BITS = 128;

	private final SecretKey key;
	private final SecureRandom random = new SecureRandom();

	public EncryptedStringConverter(AppProperties props) {
		if (props.encryptionKey() == null || props.encryptionKey().isBlank()) {
			throw new IllegalStateException("app.encryption-key is not set - add it to secrets.properties");
		}
		byte[] raw;
		try {
			raw = Base64.getDecoder().decode(props.encryptionKey().trim());
		}
		catch (IllegalArgumentException e) {
			throw new IllegalStateException("app.encryption-key must be base64", e);
		}
		if (raw.length != 32) {
			throw new IllegalStateException("app.encryption-key must decode to 32 bytes, got " + raw.length);
		}
		this.key = new SecretKeySpec(raw, "AES");
	}

	@Override
	public String convertToDatabaseColumn(String plain) {
		if (plain == null) {
			return null;
		}
		try {
			byte[] iv = new byte[IV_BYTES];
			random.nextBytes(iv);
			Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
			cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, iv));
			byte[] encrypted = cipher.doFinal(plain.getBytes(StandardCharsets.UTF_8));
			return Base64.getEncoder().encodeToString(ByteBuffer.allocate(iv.length + encrypted.length)
					.put(iv).put(encrypted).array());
		}
		catch (GeneralSecurityException e) {
			throw new IllegalStateException("Encryption failed", e);
		}
	}

	@Override
	public String convertToEntityAttribute(String stored) {
		if (stored == null) {
			return null;
		}
		try {
			byte[] all = Base64.getDecoder().decode(stored);
			Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
			cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, all, 0, IV_BYTES));
			return new String(cipher.doFinal(all, IV_BYTES, all.length - IV_BYTES), StandardCharsets.UTF_8);
		}
		catch (GeneralSecurityException | IllegalArgumentException e) {
			throw new IllegalStateException("Could not decrypt a stored token - was app.encryption-key changed?", e);
		}
	}

}
