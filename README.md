# qbittorrent-gluetun-port-sync

Synchronizes qBittorrent's listening port with the forwarded port from Gluetun VPN.

> [!NOTE]
> This project is under active development.

## Overview

When using qBittorrent behind a VPN with port forwarding (via Gluetun), the forwarded port can change whenever the VPN reconnects. If qBittorrent isn't configured to use the current forwarded port, incoming connections will fail, resulting in poor seeding performance.

This service monitors the forwarded port from Gluetun and automatically updates qBittorrent's listening port to match.

## How It Works

1. On startup, the service waits for both Gluetun and qBittorrent to become available
2. It queries Gluetun's control server API (`/v1/portforward`) for the current forwarded port
3. It compares this with qBittorrent's configured listening port
4. If they differ, it updates qBittorrent via the Web API and verifies the change
5. This check repeats at a configurable interval (default: 30 seconds)

## Usage

The service is designed to run as a Docker container alongside Gluetun and qBittorrent.

```yaml
services:
  gluetun:
    image: qmcgaw/gluetun
    cap_add:
      - NET_ADMIN
    ports:
      - "8080:8080"  # qBittorrent Web UI
      - "8000:8000"  # Gluetun control server
    environment:
      - VPN_SERVICE_PROVIDER=protonvpn
      - VPN_TYPE=wireguard
      # ... other Gluetun config

  qbittorrent:
    image: linuxserver/qbittorrent
    network_mode: "service:gluetun"
    environment:
      - WEBUI_PORT=8080
    depends_on:
      - gluetun

  port-sync:
    image: ghcr.io/bdclark/qbittorrent-gluetun-port-sync:latest
    environment:
      - GLUETUN_URL=http://gluetun:8000
      - QBITTORRENT_URL=http://gluetun:8080
      - QBITTORRENT_USERNAME=admin
      - QBITTORRENT_PASSWORD=adminadmin
    depends_on:
      - gluetun
      - qbittorrent
```

Note: Since qBittorrent uses `network_mode: "service:gluetun"`, its Web UI is accessed through the Gluetun container. The `QBITTORRENT_URL` should reference Gluetun's hostname, not qBittorrent's.

## Health Check

When enabled (default), the service exposes an HTTP health endpoint at `/health` on port 8081.

- Returns `200 OK` with `{"status": "healthy"}` when both services are reachable
- Returns `503 Service Unavailable` with `{"status": "unhealthy", "reason": "..."}` otherwise

This can be used for container orchestration health checks.

## Environment Variables

### Required

| Variable           | Description                                              |
| ------------------ | -------------------------------------------------------- |
| `GLUETUN_URL`      | Gluetun control server URL (e.g., `http://gluetun:8000`) |
| `QBITTORRENT_URL`  | qBittorrent Web UI URL (e.g., `http://gluetun:8080`)     |

### Gluetun Authentication

| Variable           | Description                        | Default |
| ------------------ | ---------------------------------- | ------- |
| `GLUETUN_API_KEY`  | API key for Gluetun control server | None    |
| `GLUETUN_USERNAME` | Username for Gluetun basic auth    | None    |
| `GLUETUN_PASSWORD` | Password for Gluetun basic auth    | None    |

If both API key and basic auth are provided, API key takes priority.

### qBittorrent Authentication

| Variable                 | Description                          | Default |
| ------------------------ | ------------------------------------ | ------- |
| `QBITTORRENT_USERNAME`   | qBittorrent Web UI username          | None    |
| `QBITTORRENT_PASSWORD`   | qBittorrent Web UI password          | None    |
| `QBITTORRENT_VERIFY_SSL` | Verify SSL certificates for HTTPS    | `true`  |

### Timing

| Variable                 | Description                                      | Default |
| ------------------------ | ------------------------------------------------ | ------- |
| `STARTUP_CHECK_DELAY`    | Seconds to wait before beginning startup checks  | `5`     |
| `STARTUP_CHECK_INTERVAL` | Seconds between readiness checks during startup  | `5`     |
| `STARTUP_MAX_ATTEMPTS`   | Maximum startup attempts before exit             | `60`    |
| `POLL_INTERVAL`          | Seconds between port checks in main loop         | `30`    |
| `VERIFY_DELAY`           | Seconds between port verification attempts       | `2`     |
| `VERIFY_MAX_ATTEMPTS`    | Maximum port verification attempts               | `3`     |
| `REQUEST_TIMEOUT`        | HTTP request timeout in seconds                  | `10`    |

### Logging & Health

| Variable         | Description                                      | Default |
| ---------------- | ------------------------------------------------ | ------- |
| `LOG_LEVEL`      | Logging level: `DEBUG`, `INFO`, `WARN`, `ERROR`  | `INFO`  |
| `HEALTH_ENABLED` | Enable health check endpoint                     | `true`  |
| `HEALTH_PORT`    | Port for health check endpoint                   | `8081`  |

## License

MIT
