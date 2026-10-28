package com.trademarkets.broker;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * The one app for all broker accounts. Lives in com.trademarkets.broker so it picks up broker-common and every
 * connector on the classpath (com.trademarkets.broker.zerodha, .angelone, ...). Accounts: accounts.properties.
 */
@SpringBootApplication
public class BrokerApplication {

	public static void main(String[] args) {
		SpringApplication.run(BrokerApplication.class, args);
	}

}
