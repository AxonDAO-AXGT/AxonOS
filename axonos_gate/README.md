# AXGT Gate for AxonOS

This module implements AXGT token-based gating for AxonOS remote desktop access.

## Overview

AxonOS access is restricted to users who hold AXGT tokens in their Ethereum wallet. The gate checks token balance before allowing WebSocket connections to the noVNC desktop.

## Configuration

Required environment variables:

- `AXGT_CONTRACT_ADDRESS`: AXGT ERC-20 contract address (default: `0x6112C3509A8a787df576028450FebB3786A2274d`)
- `AXGT_CHAIN_ID`: Ethereum chain ID (default: `1` for mainnet)
- `AXGT_RPC_URL`: Ethereum RPC endpoint (default: `https://ethereum-rpc.publicnode.com`)

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

- Wallet addresses are masked in logs (first 6 and last 4 characters shown)
- Invalid wallet formats are rejected early
- System fails closed if RPC is unavailable
- Contract address is validated against expected value

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
