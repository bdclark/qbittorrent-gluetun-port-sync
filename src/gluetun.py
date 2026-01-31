"""Gluetun control server API client."""

import logging
from dataclasses import dataclass

import requests

from .config import Config


@dataclass
class GluetunResult:
    """Result from Gluetun API call."""

    success: bool
    port: int | None = None
    error: str | None = None
    is_auth_error: bool = False


class GluetunClient:
    """Client for Gluetun control server API."""

    def __init__(self, config: Config, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self._session = requests.Session()
        self._setup_auth()

    def _setup_auth(self) -> None:
        """Configure authentication for requests."""
        if self.config.gluetun_api_key:
            self._session.headers["X-API-Key"] = self.config.gluetun_api_key
        elif self.config.gluetun_username and self.config.gluetun_password:
            self._session.auth = (
                self.config.gluetun_username,
                self.config.gluetun_password,
            )

    def get_forwarded_port(self) -> GluetunResult:
        """Get the forwarded port from Gluetun."""
        url = f"{self.config.gluetun_url}/v1/portforward"

        self.logger.debug(f"GET {url}")

        try:
            response = self._session.get(url, timeout=self.config.request_timeout)

            self.logger.debug(f"Response: {response.status_code} {response.text}")

            if response.status_code == 401:
                return GluetunResult(
                    success=False,
                    error="Authentication failed",
                    is_auth_error=True,
                )

            if response.status_code == 403:
                return GluetunResult(
                    success=False,
                    error="Access forbidden",
                    is_auth_error=True,
                )

            if response.status_code == 404:
                # VPN may not be connected
                return GluetunResult(
                    success=True,
                    port=None,
                    error="No port forwarded (VPN may be disconnected)",
                )

            if response.status_code >= 500:
                return GluetunResult(
                    success=False,
                    error=f"Server error: {response.status_code}",
                )

            if response.status_code != 200:
                return GluetunResult(
                    success=False,
                    error=f"Unexpected status: {response.status_code}",
                )

            try:
                data = response.json()
                port = data.get("port")

                if port is None or port == 0:
                    return GluetunResult(
                        success=True,
                        port=None,
                        error="No port forwarded (port forwarding not active)",
                    )

                return GluetunResult(success=True, port=int(port))

            except (ValueError, KeyError) as e:
                return GluetunResult(
                    success=False,
                    error=f"Invalid response format: {e}",
                )

        except requests.exceptions.Timeout:
            return GluetunResult(success=False, error="Request timed out")

        except requests.exceptions.ConnectionError as e:
            return GluetunResult(success=False, error=f"Connection error: {e}")

        except requests.exceptions.RequestException as e:
            return GluetunResult(success=False, error=f"Request failed: {e}")

    def check_ready(self) -> GluetunResult:
        """Check if Gluetun is ready and responding."""
        return self.get_forwarded_port()
