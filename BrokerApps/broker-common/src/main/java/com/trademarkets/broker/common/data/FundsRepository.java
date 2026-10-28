package com.trademarkets.broker.common.data;

import java.time.Instant;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface FundsRepository extends JpaRepository<FundsSnapshot, Long> {

	@Modifying
	@Query("delete from FundsSnapshot s where s.takenAt < :cutoff")
	int deleteOlderThan(@Param("cutoff") Instant cutoff);

}
