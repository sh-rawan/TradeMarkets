package com.trademarkets.broker.common.data;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

import com.trademarkets.broker.common.account.BrokerAccount;

public interface OrderRepository extends JpaRepository<OrderRecord, Long> {

	Optional<OrderRecord> findByAccountAndOrderId(BrokerAccount account, String orderId);

}
