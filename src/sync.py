"""Main synchronization logic and entry point."""

import logging
import sys
import time

from .config import Config, load_config, setup_logging
from .gluetun import GluetunClient
from .health import HealthServer, HealthState
from .qbittorrent import QBittorrentClient


class PortSync:
    """Main port synchronization orchestrator."""

    def __init__(
        self,
        config: Config,
        logger: logging.Logger,
        gluetun: GluetunClient,
        qbittorrent: QBittorrentClient,
        health_state: HealthState,
    ):
        self.config = config
        self.logger = logger
        self.gluetun = gluetun
        self.qbittorrent = qbittorrent
        self.health_state = health_state

    def wait_for_services(self) -> bool:
        """Wait for both services to be ready. Returns True if successful."""
        self.logger.info("Waiting for services to be ready...")

        gluetun_ready = False
        qbittorrent_ready = False

        for attempt in range(1, self.config.startup_max_attempts + 1):
            # Check Gluetun
            if not gluetun_ready:
                self.logger.info(
                    f"Checking Gluetun... (attempt {attempt}/{self.config.startup_max_attempts})"
                )
                result = self.gluetun.check_ready()

                if result.is_auth_error:
                    self.logger.error(f"Gluetun authentication failed: {result.error}")
                    return False

                if result.success:
                    self.logger.info("Gluetun is ready")
                    gluetun_ready = True
                else:
                    self.logger.debug(f"Gluetun not ready: {result.error}")

            # Check qBittorrent
            if not qbittorrent_ready:
                self.logger.info(
                    f"Checking qBittorrent... (attempt {attempt}/{self.config.startup_max_attempts})"
                )
                result = self.qbittorrent.check_ready()

                if result.is_auth_error:
                    self.logger.error(
                        f"qBittorrent authentication failed: {result.error}"
                    )
                    return False

                if result.success:
                    self.logger.info("qBittorrent is ready")
                    qbittorrent_ready = True
                else:
                    self.logger.debug(f"qBittorrent not ready: {result.error}")

            # Both ready?
            if gluetun_ready and qbittorrent_ready:
                self.logger.info("Both services ready")
                self.health_state.set_service_status(True, True)
                return True

            # Wait before next attempt
            if attempt < self.config.startup_max_attempts:
                time.sleep(self.config.startup_check_interval)

        self.logger.error(
            f"Services not ready after {self.config.startup_max_attempts} attempts"
        )
        return False

    def sync_port(self) -> bool:
        """
        Perform a single port sync cycle.
        Returns True if sync was successful (or no update needed).
        """
        # Get forwarded port from Gluetun
        gluetun_result = self.gluetun.get_forwarded_port()

        if gluetun_result.is_auth_error:
            self.logger.error(f"Gluetun auth error: {gluetun_result.error}")
            self.health_state.set_healthy(False, f"Gluetun auth error: {gluetun_result.error}")
            return False

        if not gluetun_result.success:
            self.logger.warning(f"Failed to get Gluetun port: {gluetun_result.error}")
            self.health_state.set_service_status(False, True)
            return False

        if gluetun_result.port is None:
            self.logger.warning("No port forwarded (VPN may be disconnected)")
            self.health_state.set_service_status(True, True)
            return True  # Not an error, just no port to sync

        gluetun_port = gluetun_result.port

        # Get current qBittorrent port
        qbt_result = self.qbittorrent.get_listen_port()

        if qbt_result.is_auth_error:
            self.logger.error(f"qBittorrent auth error: {qbt_result.error}")
            self.health_state.set_healthy(False, f"qBittorrent auth error: {qbt_result.error}")
            return False

        if not qbt_result.success:
            self.logger.warning(f"Failed to get qBittorrent port: {qbt_result.error}")
            self.health_state.set_service_status(True, False)
            return False

        current_port = qbt_result.port
        self.health_state.set_service_status(True, True)

        # Compare and update if needed
        if current_port == gluetun_port:
            self.logger.info(f"Port unchanged ({current_port})")
            return True

        self.logger.info(
            f"Port changed: {current_port} -> {gluetun_port}, updating qBittorrent"
        )

        # Update port
        update_result = self.qbittorrent.set_listen_port(gluetun_port)

        if not update_result.success:
            self.logger.error(f"Failed to update port: {update_result.error}")
            # Continue to verification anyway

        # Verify update with retries
        for attempt in range(1, self.config.verify_max_attempts + 1):
            time.sleep(self.config.verify_delay)

            verify_result = self.qbittorrent.get_listen_port()

            if not verify_result.success:
                self.logger.warning(
                    f"Failed to verify port update (attempt {attempt}/{self.config.verify_max_attempts}): {verify_result.error}"
                )
                continue

            if verify_result.port == gluetun_port:
                self.logger.info(f"Port updated successfully to {gluetun_port}")
                return True

            self.logger.debug(
                f"Port not yet updated (attempt {attempt}/{self.config.verify_max_attempts}): expected {gluetun_port}, got {verify_result.port}"
            )

        # All attempts exhausted
        self.logger.warning(
            f"Port verification failed after {self.config.verify_max_attempts} attempts: expected {gluetun_port}, got {verify_result.port}"
        )
        return False

    def run(self) -> None:
        """Run the main sync loop."""
        self.logger.info("Starting port sync loop")

        while True:
            try:
                self.sync_port()
            except Exception as e:
                self.logger.error(f"Unexpected error in sync loop: {e}")
                self.health_state.set_healthy(False, str(e))

            self.logger.debug(f"Sleeping for {self.config.poll_interval}s")
            time.sleep(self.config.poll_interval)


def main() -> None:
    """Application entry point."""
    # Load configuration
    config = load_config()

    # Set up logging
    logger = setup_logging(config.log_level)

    logger.info("Starting qBittorrent-Gluetun Port Sync")
    config.log_config(logger)

    # Initialize health state and server
    health_state = HealthState()

    if config.health_enabled:
        health_server = HealthServer(config.health_port, health_state, logger)
        health_server.start()

    # Initialize clients
    gluetun = GluetunClient(config, logger)
    qbittorrent = QBittorrentClient(config, logger)

    # Create sync orchestrator
    sync = PortSync(config, logger, gluetun, qbittorrent, health_state)

    # Initial delay before startup checks
    if config.startup_check_delay > 0:
        logger.info(f"Waiting {config.startup_check_delay}s before startup checks...")
        time.sleep(config.startup_check_delay)

    # Wait for services
    if not sync.wait_for_services():
        logger.error("Startup failed, exiting")
        sys.exit(1)

    # Perform initial sync
    logger.info("Performing initial port sync")
    sync.sync_port()

    # Enter main loop
    sync.run()


if __name__ == "__main__":
    main()
