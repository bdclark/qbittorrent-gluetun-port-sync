"""qBittorrent Web API client."""

import json
import logging
from dataclasses import dataclass
from typing import Any

import requests

from .config import Config


@dataclass
class QBittorrentResult:
    """Result from qBittorrent API call."""

    success: bool
    port: int | None = None
    error: str | None = None
    is_auth_error: bool = False


class QBittorrentClient:
    """Client for qBittorrent Web API."""

    def __init__(self, config: Config, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self._session = requests.Session()
        self._authenticated = False

    def _login(self) -> QBittorrentResult:
        """Authenticate with qBittorrent if credentials are configured."""
        if not self.config.qbittorrent_username:
            self._authenticated = True
            return QBittorrentResult(success=True)

        if self._authenticated:
            return QBittorrentResult(success=True)

        url = f"{self.config.qbittorrent_url}/api/v2/auth/login"

        self.logger.debug(f"POST {url} (login)")

        try:
            response = self._session.post(
                url,
                data={
                    "username": self.config.qbittorrent_username,
                    "password": self.config.qbittorrent_password,
                },
                timeout=self.config.request_timeout,
                verify=self.config.qbittorrent_verify_ssl,
            )

            self.logger.debug(f"Response: {response.status_code} {response.text}")

            if response.status_code == 403:
                return QBittorrentResult(
                    success=False,
                    error="Authentication failed",
                    is_auth_error=True,
                )

            if response.status_code != 200:
                return QBittorrentResult(
                    success=False,
                    error=f"Login failed: {response.status_code}",
                )

            if response.text.strip().lower() != "ok.":
                return QBittorrentResult(
                    success=False,
                    error="Authentication failed (invalid credentials)",
                    is_auth_error=True,
                )

            self._authenticated = True
            self.logger.debug("qBittorrent login successful")
            return QBittorrentResult(success=True)

        except requests.exceptions.Timeout:
            return QBittorrentResult(success=False, error="Login request timed out")

        except requests.exceptions.ConnectionError as e:
            return QBittorrentResult(success=False, error=f"Connection error: {e}")

        except requests.exceptions.RequestException as e:
            return QBittorrentResult(success=False, error=f"Login request failed: {e}")

    def _request(
        self,
        method: str,
        endpoint: str,
        retry_auth: bool = True,
        **kwargs: Any,
    ) -> tuple[requests.Response | None, QBittorrentResult | None]:
        """
        Make authenticated request with auto re-auth on 403.

        Returns (response, None) on success, or (None, error_result) on failure.
        """
        login_result = self._login()
        if not login_result.success:
            return None, login_result

        url = f"{self.config.qbittorrent_url}{endpoint}"
        self.logger.debug(f"{method.upper()} {url}")

        try:
            response = self._session.request(
                method,
                url,
                timeout=self.config.request_timeout,
                verify=self.config.qbittorrent_verify_ssl,
                **kwargs,
            )

            self.logger.debug(f"Response: {response.status_code}")

            if response.status_code == 403 and retry_auth:
                self.logger.debug("Got 403, retrying with fresh login")
                self._authenticated = False
                return self._request(method, endpoint, retry_auth=False, **kwargs)

            return response, None

        except requests.exceptions.Timeout:
            return None, QBittorrentResult(success=False, error="Request timed out")

        except requests.exceptions.ConnectionError as e:
            return None, QBittorrentResult(success=False, error=f"Connection error: {e}")

        except requests.exceptions.RequestException as e:
            return None, QBittorrentResult(success=False, error=f"Request failed: {e}")

    def get_listen_port(self) -> QBittorrentResult:
        """Get the current listening port from qBittorrent."""
        response, error = self._request("GET", "/api/v2/app/preferences")

        if error:
            return error

        if response.status_code != 200:
            return QBittorrentResult(
                success=False,
                error=f"Failed to get preferences: {response.status_code}",
            )

        try:
            data = response.json()
            port = data.get("listen_port")

            if port is None:
                return QBittorrentResult(
                    success=False,
                    error="listen_port not in response",
                )

            self.logger.debug(f"Current listen port: {port}")
            return QBittorrentResult(success=True, port=int(port))

        except (ValueError, KeyError) as e:
            return QBittorrentResult(
                success=False,
                error=f"Invalid response format: {e}",
            )

    def set_listen_port(self, port: int) -> QBittorrentResult:
        """Set the listening port in qBittorrent."""
        self.logger.debug(f"Setting listen_port={port}")

        response, error = self._request(
            "POST",
            "/api/v2/app/setPreferences",
            data={"json": json.dumps({"listen_port": port})},
        )

        if error:
            return error

        if response.status_code != 200:
            return QBittorrentResult(
                success=False,
                error=f"Failed to set port: {response.status_code}",
            )

        return QBittorrentResult(success=True, port=port)

    def check_ready(self) -> QBittorrentResult:
        """Check if qBittorrent is ready and responding."""
        return self.get_listen_port()
