# AXGT Gate for AxonOS

This module implements AXGT token-based gating for AxonOS remote desktop access.

## Official References

- **AxonDAO website**: `https://axondao.io`
- **AXGT contract (Ethereum mainnet)**: `0x6112C3509A8a787df576028450FebB3786A2274d`
- **Explorer**: `https://etherscan.io/address/0x6112C3509A8a787df576028450FebB3786A2274d`

## Overview

AxonOS access uses a hold-based, off-chain credit model:

- Wallet must hold at least the configured AXGT minimum.
- Usage is metered per wallet globally (across sessions/devices), with no on-chain debit/transfer.
- Credit capacity scales linearly with holdings (`100 AXGT = 60 minutes` by default).
- Access locks automatically when wallet credit is exhausted.

## Configuration

Required environment variables:

- `AXGT_CONTRACT_ADDRESS`: AXGT ERC-20 contract address
- `AXGT_CHAIN_ID`: Ethereum chain ID
- `AXGT_RPC_URL`: Ethereum RPC endpoint

Optional hardening environment variables:

- `AXGT_CORS_ORIGINS`: CORS allowlist for `/api/auth/verify-wallet`. Use comma-separated origins (exact match) or `*` to allow any. Default: same-origin only.
- `AXGT_RATE_LIMIT_PER_MIN`: Best-effort per-client rate limit for verify calls. Default: `60`. Set `0` to disable.
- `AXGT_MIN_HOLD_AMOUNT`: Minimum AXGT required for access, in token units (e.g. `100` means 100 AXGT). Default: `100`.
- `AXGT_CREDIT_PER_100_AXGT_MINUTES`: Minutes of usage credit granted per 100 AXGT held. Default: `60`.
- `AXGT_WARNING_THRESHOLD_MINUTES`: Warning threshold used by API/UI lockout warnings. Default: `10`.
- `AXGT_USAGE_DB_PATH`: Persistent per-wallet usage ledger path (JSON). Default: `/var/lib/axonos_gate/usage.json`.
- `AXGT_AUTH_TOKEN_TTL_SECONDS`: Short-lived websocket auth token TTL in seconds; token is rotated during active status polling. Default: `300`.
- `AXGT_CHALLENGE_TTL_SECONDS`: One-time sign-to-verify challenge TTL in seconds. Default: `180`.
- `AXGT_AUTH_COOKIE_NAME`: HttpOnly auth cookie name used for websocket auth. Default: `axgt_auth_token`.
- `AXGT_AUTH_COOKIE_SECURE`: Add `Secure` flag to auth cookie (`true/false`). Set `true` behind HTTPS.
- `AXGT_USAGE_RETENTION_DAYS`: Cleanup window for stale wallet usage entries. Default: `180`.
- `AXGT_EXPECTED_CONTRACT_ADDRESS`: Optional safety check; if set, the gate will only accept this contract address.

Additional configuration for websockify:

- `WEBSOCKIFY_PORT`: Port for websockify server (default: `6080`)
- `VNC_HOST`: VNC server host (default: `localhost`)
- `VNC_PORT`: VNC server port (default: `5901`)
- `NOVNC_WEB_DIR`: Directory containing noVNC web files (default: `/usr/share/novnc`)

## Components

- `axgt_verifier.py`: Core wallet verification logic using Ethereum RPC
- `websockify_gate.py`: WebSocket gate wrapper for websockify
- `gate_server.py`: HTTP server for serving HTML and API endpoints

## API Endpoints

### POST /api/auth/verify-wallet

Verify wallet hold + credit state.

**Request:**
```json
{
  "wallet_address": "0x...",
  "message": "challenge text from /api/auth/challenge",
  "signature": "0x..."
}
```

**Response:**
```json
{
  "verified": true,
  "access_type": "holding_credit",
  "locked": false,
  "auth_token": "token_value_here",
  "auth_token_expires_in_seconds": 300,
  "remaining_minutes": 42.5,
  "consumed_minutes": 17.5,
  "capacity_minutes": 60.0,
  "warning_threshold_minutes": 10,
  "min_hold_amount": "100",
  "credit_per_100_axgt_minutes": 60,
  "balance_axgt": "142.0"
}
```

or

```json
{
  "verified": false,
  "locked": true,
  "remaining_minutes": 0.0,
  "error": "Usage credit exhausted. Increase held AXGT to raise capacity and unlock access."
}
```

### GET /api/auth/wallet-status

Get current wallet credit status for warning/lock overlays.

**Query:**
- `wallet_address=0x...` (or `wallet` alias)
**Headers (required):**
- `X-AXGT-Auth-Token: <token from verify-wallet>` to authorize status checks and rotate session token.

**Response:**
```json
{
  "verified": true,
  "access_type": "holding_credit",
  "locked": false,
  "remaining_minutes": 9.8,
  "consumed_minutes": 50.2,
  "capacity_minutes": 60.0,
  "warning_threshold_minutes": 10,
  "reason": "Warning: less than 10 minutes of AXGT usage credit remaining."
}
```

### GET /api/auth/challenge

Issue a one-time wallet-bound challenge for `personal_sign`.

**Query:**
- `wallet_address=0x...` (or `wallet` alias)

**Response:**
```json
{
  "challenge": "AxonOS verify\nWallet: 0x...\nNonce: ...\nIssuedAt: ...",
  "challenge_expires_in_seconds": 180
}
```

## Security

- The gate uses wallet-bound one-time challenge nonces to reduce signature replay risk.
- WebSocket auth tokens are transported via HttpOnly cookies (not URL query strings).
- Wallet status polling requires a valid auth token, preventing unauthenticated usage metering.
- The gate performs basic input validation and avoids logging full wallet addresses.

## Installation

1. Install dependencies:
```bash
pip3 install -r requirements.txt
```

2. Set environment variables (see Configuration above)

3. Run the gate server:
```bash
python3 websockify_gate.py
```

The server will start on port 6080 (or configured port) and gate all WebSocket connections.
