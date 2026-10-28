package com.trademarkets.broker.common.data;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import com.trademarkets.broker.common.config.SyncProperties;

/** Runs the sync on the cron schedules in sync.properties. Off when sync.enabled=false. */
@Component
@ConditionalOnProperty(name = "sync.enabled", havingValue = "true", matchIfMissing = true)
class SyncScheduler {

	private final SyncService sync;
	private final SyncProperties props;

	SyncScheduler(SyncService sync, SyncProperties props) {
		this.sync = sync;
		this.props = props;
	}

	@EventListener(ApplicationReadyEvent.class)
	void onStartup() {
		if (props.onStartup()) {
			sync.syncAll();
		}
	}

	@Scheduled(cron = "${sync.cron:0 */15 9-15 * * MON-FRI}", zone = "${sync.zone:Asia/Kolkata}")
	void scheduled() {
		sync.syncAll();
	}

	@Scheduled(cron = "${sync.cleanup-cron:0 30 18 * * *}", zone = "${sync.zone:Asia/Kolkata}")
	void cleanup() {
		sync.deleteOldSnapshots();
	}

}
