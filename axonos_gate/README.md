# AXGT Gate for AxonOS

This module implements AXGT token-based gating for AxonOS remote desktop access.

## Official References

- **AxonDAO website**: `https://axondao.io`
- **AXGT contract (Ethereum mainnet)**: `0x6112C3509A8a787df576028450FebB3786A2274d`
- **Explorer**: `https://etherscan.io/address/0x6112C3509A8a787df576028450FebB3786A2274d`

## Overview

AxonOS access is restricted to users who hold AXGT tokens in their Ethereum wallet. The gate checks token balance before allowing WebSocket connections to the noVNC desktop.

## Configuration

Required environment variables:

- `AXGT_CONTRACT_ADDRESS`: AXGT ERC-20 contract address
- `AXGT_CHAIN_ID`: Ethereum chain ID
- `AXGT_RPC_URL`: Ethereum RPC endpoint

Optional hardening environment variables:

- `AXGT_CORS_ORIGINS`: CORS allowlist for `/api/auth/verify-wallet`. Use comma-separated origins (exact match) or `*` to allow any. Default: same-origin only.
- `AXGT_RATE_LIMIT_PER_MIN`: Best-effort per-client rate limit for verify calls. Default: `60`. Set `0` to disable.
- `AXGT_TRIAL_DB_PATH`: Persistent trial registry path (JSON). Default: `/var/lib/axonos_gate/trials.json`
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

Verify if a wallet holds AXGT tokens.

**Request:**
```json
{
  "wallet_address": "0x..."
}
```

**Response:**
```json
{
  "verified": true
}
```

or

```json
{
  "verified": false,
  "error": "No AXGT balance found in this wallet"
}
```

## Security

- The gate performs basic input validation and avoids logging full wallet addresses.
- The verification path is designed to behave conservatively if upstream dependencies (e.g., RPC) are unavailable.

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
