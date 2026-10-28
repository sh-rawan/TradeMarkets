package com.trademarkets.broker.common.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/** sync.* settings (sync.properties). The cron expressions are read directly by SyncScheduler. */
@ConfigurationProperties("sync")
public record SyncProperties(@DefaultValue("true") boolean enabled, @DefaultValue("true") boolean onStartup,
		@DefaultValue("90") int retentionDays) {
}
