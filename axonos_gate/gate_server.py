#!/usr/bin/env python3
"""
AXGT Gate Server - Simple Implementation

Serves HTTP (HTML/API) and gates WebSocket connections to websockify.
"""

import os
import sys
import logging
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

from security_utils import cors_origin_for_request, get_rate_limiter_from_env, parse_cors_allowlist

# Add /axonos_gate to path for imports
_script_dir = os.path.dirname(os.path.abspath(__file__))
if '/axonos_gate' not in sys.path:
    sys.path.insert(0, '/axonos_gate')

# Import our modules
try:
    from axgt_verifier import has_access, validate_wallet_address, mask_wallet_address
except ImportError:
    # Fallback to package import
    try:
        from axonos_gate.axgt_verifier import has_access, validate_wallet_address, mask_wallet_address
    except ImportError as e:
        print(f"ERROR: Cannot import axgt_verifier: {e}", file=sys.stderr)
        sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
# CORS: default is same-origin (no wildcard). For unusual deployments, set AXGT_CORS_ORIGINS
# to "*" or a comma-separated list of allowed origins.
_allow_any, _allowlist = parse_cors_allowlist(os.getenv("AXGT_CORS_ORIGINS"))
# Keep flask-cors installed but don't let it default to "*".
CORS(app, resources={r"/api/*": {"origins": []}})

_rate_limiter = get_rate_limiter_from_env()

NOVNC_WEB_DIR = Path('/usr/share/novnc')

@app.after_request
def after_request(response):
    """Add CORS headers to all responses."""
    origin = cors_origin_for_request(
        request.headers.get("Origin"),
        request.headers.get("Host"),
        _allow_any,
        _allowlist,
    )
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Wallet-Address"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    return response

@app.route('/api/auth/verify-wallet', methods=['POST', 'OPTIONS'])
def verify_wallet():
    """Verify wallet holds AXGT tokens."""
    if request.method == 'OPTIONS':
        return '', 200
    try:
        # Best-effort rate limiting (per client IP)
        if _rate_limiter is not None:
            client_ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "unknown").split(",")[0].strip()
            if not _rate_limiter.allow(client_ip):
                return jsonify({"verified": False, "error": "Rate limit exceeded"}), 429

        data = request.get_json()
        if not data:
            return jsonify({'verified': False, 'error': 'No JSON data provided'}), 400
        
        wallet_address = data.get('wallet_address', '').strip()
        
        if not wallet_address:
            return jsonify({'verified': False, 'error': 'wallet_address is required'}), 400
        
        if not validate_wallet_address(wallet_address):
            return jsonify({
                'verified': False,
                'error': 'Invalid wallet address format. Must be 0x followed by 40 hex characters.'
            }), 400
        
        has_access_result, access_type, days_remaining = has_access(wallet_address)
        
        if has_access_result:
            response_data = {
                'verified': True,
                'access_type': access_type
            }
            if access_type == 'trial' and days_remaining is not None:
                response_data['trial_days_remaining'] = round(days_remaining, 1)
                response_data['message'] = f'7-day trial active ({days_remaining:.1f} days remaining)'
            elif access_type == 'balance':
                response_data['message'] = 'Wallet verified - AXGT holder'
            
            logger.info(f"Wallet verified: {mask_wallet_address(wallet_address)} (access_type: {access_type})")
            return jsonify(response_data)
        else:
            logger.info(f"Wallet verification failed: {mask_wallet_address(wallet_address)}")
            return jsonify({
                'verified': False,
                'error': 'No access available for this wallet'
            })
            
    except Exception as e:
        logger.error(f"Error in verify_wallet: {e}", exc_info=True)
        return jsonify({'verified': False, 'error': 'Internal server error'}), 500

@app.route('/')
def index():
    """Serve the main noVNC HTML page."""
    return send_from_directory(str(NOVNC_WEB_DIR), 'vnc.html')

@app.route('/<path:path>')
def serve_static(path):
    """Serve static files from noVNC directory."""
    return send_from_directory(str(NOVNC_WEB_DIR), path)

def main():
    """Run the gate server."""
    # Defaults chosen to avoid collisions with IPFS gateway (8080) and reduce surface area.
    # Override via env for non-default deployments.
    host = os.getenv('GATE_HOST', '127.0.0.1')
    port = int(os.getenv('GATE_PORT', '8889'))
    
    logger.info(f"Starting AxonOS AXGT Gate Server on {host}:{port}")
    logger.info(f"AXGT Contract: {(os.getenv('AXGT_CONTRACT_ADDRESS') or '<unset>').strip()}")
    logger.info(f"RPC URL: {(os.getenv('AXGT_RPC_URL') or '<unset>').strip()}")
    
    app.run(host=host, port=port, debug=False, use_reloader=False)

if __name__ == '__main__':
    main()
