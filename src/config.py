"""Configuration management via environment variables."""

import logging
import os
import sys
from urllib.parse import urlparse


class Config:
    """Application configuration from environment variables."""

    def __init__(self):
        # Required
        self.gluetun_url = os.environ.get("GLUETUN_URL", "").rstrip("/")
        self.qbittorrent_url = os.environ.get("QBITTORRENT_URL", "").rstrip("/")

        # Gluetun authentication
        self.gluetun_api_key = os.environ.get("GLUETUN_API_KEY")
        self.gluetun_username = os.environ.get("GLUETUN_USERNAME")
        self.gluetun_password = os.environ.get("GLUETUN_PASSWORD")

        # qBittorrent authentication
        self.qbittorrent_username = os.environ.get("QBITTORRENT_USERNAME")
        self.qbittorrent_password = os.environ.get("QBITTORRENT_PASSWORD")
        self.qbittorrent_verify_ssl = os.environ.get(
            "QBITTORRENT_VERIFY_SSL", "true"
        ).lower() in ("true", "1", "yes")

        # Timing
        self.startup_check_delay = int(os.environ.get("STARTUP_CHECK_DELAY", "5"))
        self.startup_check_interval = int(
            os.environ.get("STARTUP_CHECK_INTERVAL", "5")
        )
        self.startup_max_attempts = int(os.environ.get("STARTUP_MAX_ATTEMPTS", "60"))
        self.poll_interval = int(os.environ.get("POLL_INTERVAL", "30"))
        self.verify_delay = int(os.environ.get("VERIFY_DELAY", "2"))
        self.verify_max_attempts = int(os.environ.get("VERIFY_MAX_ATTEMPTS", "3"))
        self.request_timeout = int(os.environ.get("REQUEST_TIMEOUT", "10"))

        # Logging and health
        self.log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
        self.health_enabled = os.environ.get("HEALTH_ENABLED", "true").lower() in (
            "true",
            "1",
            "yes",
        )
        self.health_port = int(os.environ.get("HEALTH_PORT", "8081"))

    def validate(self) -> list[str]:
        """Validate configuration, returning list of errors."""
        errors = []

        if not self.gluetun_url:
            errors.append("GLUETUN_URL is required")
        elif not self._is_valid_url(self.gluetun_url):
            errors.append(f"GLUETUN_URL is not a valid URL: {self.gluetun_url}")

        if not self.qbittorrent_url:
            errors.append("QBITTORRENT_URL is required")
        elif not self._is_valid_url(self.qbittorrent_url):
            errors.append(f"QBITTORRENT_URL is not a valid URL: {self.qbittorrent_url}")

        if self.log_level not in ("DEBUG", "INFO", "WARN", "WARNING", "ERROR"):
            errors.append(f"LOG_LEVEL must be DEBUG, INFO, WARN, or ERROR: {self.log_level}")

        return errors

    def _is_valid_url(self, url: str) -> bool:
        """Check if URL is valid."""
        try:
            result = urlparse(url)
            return all([result.scheme in ("http", "https"), result.netloc])
        except Exception:
            return False

    def log_config(self, logger: logging.Logger) -> None:
        """Log configuration values, masking sensitive data."""
        logger.info(f"Gluetun URL: {self.gluetun_url}")
        logger.info(f"qBittorrent URL: {self.qbittorrent_url}")

        if self.gluetun_api_key:
            logger.info("Gluetun auth: API key")
        elif self.gluetun_username:
            logger.info(f"Gluetun auth: Basic auth (user: {self.gluetun_username})")
        else:
            logger.info("Gluetun auth: None")

        if self.qbittorrent_username:
            logger.info(f"qBittorrent auth: Enabled (user: {self.qbittorrent_username})")
        else:
            logger.info("qBittorrent auth: Disabled")

        logger.info(f"Poll interval: {self.poll_interval}s")
        logger.info(f"Startup check delay: {self.startup_check_delay}s")
        logger.info(f"Startup check interval: {self.startup_check_interval}s")
        logger.info(f"Startup max attempts: {self.startup_max_attempts}")
        logger.info(f"Request timeout: {self.request_timeout}s")
        logger.info(f"Health endpoint: {'enabled' if self.health_enabled else 'disabled'}")
        if self.health_enabled:
            logger.info(f"Health port: {self.health_port}")


def setup_logging(level: str) -> logging.Logger:
    """Configure and return the application logger."""
    # Map WARN to WARNING for logging module
    if level == "WARN":
        level = "WARNING"

    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    return logging.getLogger("port-sync")


def load_config() -> Config:
    """Load and validate configuration, exit on errors."""
    config = Config()
    errors = config.validate()

    if errors:
        # Set up minimal logging to report errors
        logger = setup_logging("ERROR")
        for error in errors:
            logger.error(error)
        sys.exit(1)

    return config
