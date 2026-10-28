package com.trademarkets.broker.common.account;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface AccountRepository extends JpaRepository<BrokerAccount, Long> {

	Optional<BrokerAccount> findByBrokerAndName(String broker, String name);

}
