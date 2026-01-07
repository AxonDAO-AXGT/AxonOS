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
# Configure CORS to allow requests from the noVNC origin
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

NOVNC_WEB_DIR = Path('/usr/share/novnc')

@app.after_request
def after_request(response):
    """Add CORS headers to all responses."""
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
    return response

@app.route('/api/auth/verify-wallet', methods=['POST', 'OPTIONS'])
def verify_wallet():
    """Verify wallet holds AXGT tokens."""
    if request.method == 'OPTIONS':
        return '', 200
    try:
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
    host = os.getenv('GATE_HOST', '0.0.0.0')
    port = int(os.getenv('GATE_PORT', '8080'))  # Default to 8080, not 6080
    
    logger.info(f"Starting AxonOS AXGT Gate Server on {host}:{port}")
    logger.info(f"AXGT Contract: {os.getenv('AXGT_CONTRACT_ADDRESS', '0x6112C3509A8a787df576028450FebB3786A2274d')}")
    logger.info(f"RPC URL: {os.getenv('AXGT_RPC_URL', 'https://ethereum-rpc.publicnode.com')}")
    
    app.run(host=host, port=port, debug=False, use_reloader=False)

if __name__ == '__main__':
    main()
