#!/usr/bin/env python3
"""
AxonOS AXGT Gate Server

Serves the noVNC interface and gates WebSocket connections based on AXGT token ownership.
"""

import os
import logging
import asyncio
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# Import our modules (support running as a script in /axonos_gate)
try:
    from axgt_verifier import has_axgt_balance, validate_wallet_address, mask_wallet_address
    from security_utils import cors_origin_for_request, get_rate_limiter_from_env, parse_cors_allowlist
except ImportError:
    # Fallback to package import (support running as module)
    from axonos_gate.axgt_verifier import has_axgt_balance, validate_wallet_address, mask_wallet_address
    from axonos_gate.security_utils import cors_origin_for_request, get_rate_limiter_from_env, parse_cors_allowlist

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
# CORS: default is same-origin only. Configure AXGT_CORS_ORIGINS for unusual deployments.
_allow_any, _allowlist = parse_cors_allowlist(os.getenv("AXGT_CORS_ORIGINS"))
CORS(app, resources={r"/api/*": {"origins": []}})
_rate_limiter = get_rate_limiter_from_env()

# Configuration
NOVNC_WEB_DIR = Path('/usr/share/novnc')
WEBSOCKIFY_INTERNAL = 'ws://localhost:6081/websockify'  # Internal websockify (not exposed)

# Ensure we have the web directory
if not NOVNC_WEB_DIR.exists():
    logger.warning(f"noVNC web directory not found: {NOVNC_WEB_DIR}")

@app.route('/api/auth/verify-wallet', methods=['POST'])
def verify_wallet():
    """Verify wallet holds AXGT tokens."""
    try:
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
        
        # Validate format
        if not validate_wallet_address(wallet_address):
            return jsonify({
                'verified': False,
                'error': 'Invalid wallet address format. Must be 0x followed by 40 hex characters.'
            }), 400
        
        # Check balance
        has_balance = has_axgt_balance(wallet_address)
        
        if has_balance:
            logger.info(f"Wallet verified: {mask_wallet_address(wallet_address)}")
            return jsonify({'verified': True})
        else:
            logger.info(f"Wallet verification failed: {mask_wallet_address(wallet_address)}")
            return jsonify({
                'verified': False,
                'error': 'No AXGT balance found in this wallet'
            })
            
    except Exception as e:
        logger.error(f"Error in verify_wallet: {e}", exc_info=True)
        return jsonify({'verified': False, 'error': 'Internal server error'}), 500


@app.after_request
def after_request(response):
    """Emit CORS headers only when appropriate (avoid wildcard by default)."""
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

@app.route('/')
def index():
    """Serve the main noVNC HTML page."""
    return send_from_directory(str(NOVNC_WEB_DIR), 'vnc.html')

@app.route('/<path:path>')
def serve_static(path):
    """Serve static files from noVNC directory."""
    return send_from_directory(str(NOVNC_WEB_DIR), path)

async def handle_websocket(websocket, path):
    """Handle WebSocket connection with wallet verification."""
    # Extract wallet from query string
    parsed = urlparse(path)
    query_params = parse_qs(parsed.query)
    wallet_address = query_params.get('wallet', [None])[0]
    
    # Also check headers
    if not wallet_address:
        wallet_address = websocket.request_headers.get('X-Wallet-Address')
    
    if not wallet_address:
        logger.warning("WebSocket connection rejected: no wallet address")
        await websocket.close(code=403, reason="Wallet address required")
        return
    
    wallet_address = wallet_address.strip()
    
    # Validate format
    if not validate_wallet_address(wallet_address):
        logger.warning(f"WebSocket connection rejected: invalid format: {mask_wallet_address(wallet_address)}")
        await websocket.close(code=403, reason="Invalid wallet address format")
        return
    
    # Check AXGT balance
    if not has_axgt_balance(wallet_address):
        logger.warning(f"WebSocket connection rejected: no AXGT: {mask_wallet_address(wallet_address)}")
        await websocket.close(code=403, reason="Wallet does not hold AXGT tokens")
        return
    
    logger.info(f"WebSocket connection approved: {mask_wallet_address(wallet_address)}")
    
    # Proxy to internal websockify
    try:
        import websockets
        async with websockets.connect(WEBSOCKIFY_INTERNAL) as ws_internal:
            # Bidirectional proxy
            async def proxy_to_internal():
                try:
                    async for message in websocket:
                        await ws_internal.send(message)
                except websockets.exceptions.ConnectionClosed:
                    pass
            
            async def proxy_from_internal():
                try:
                    async for message in ws_internal:
                        await websocket.send(message)
                except websockets.exceptions.ConnectionClosed:
                    pass
            
            await asyncio.gather(
                proxy_to_internal(),
                proxy_from_internal()
            )
    except Exception as e:
        logger.error(f"Error proxying WebSocket: {e}", exc_info=True)
        await websocket.close(code=500, reason="Internal server error")

def run_websocket_server(host='0.0.0.0', port=6080):
    """Run WebSocket gate server."""
    try:
        import websockets
        start_server = websockets.serve(handle_websocket, host, port)
        logger.info(f"WebSocket gate server started on {host}:{port}")
        asyncio.get_event_loop().run_until_complete(start_server)
        asyncio.get_event_loop().run_forever()
    except ImportError:
        logger.error("websockets library not available. Install with: pip install websockets")
    except Exception as e:
        logger.error(f"Error starting WebSocket server: {e}", exc_info=True)

def run_server(host='0.0.0.0', port=6080):
    """Run the Flask server with WebSocket gate."""
    logger.info(f"Starting AxonOS AXGT Gate Server on {host}:{port}")
    logger.info(f"AXGT Contract: {os.getenv('AXGT_CONTRACT_ADDRESS', '0x6112C3509A8a787df576028450FebB3786A2274d')}")
    logger.info(f"RPC URL: {os.getenv('AXGT_RPC_URL', 'https://ethereum-rpc.publicnode.com')}")
    
    # Start WebSocket gate server in a separate thread
    ws_thread = threading.Thread(target=run_websocket_server, args=(host, port), daemon=True)
    ws_thread.start()
    
    # Run Flask app for HTTP (HTML and API) on a different port
    # Actually, we need to serve both HTTP and WS on the same port
    # So we'll use gevent with WebSocket support
    try:
        from gevent import pywsgi
        from geventwebsocket.handler import WebSocketHandler
        from geventwebsocket import WebSocketError
        
        class WebSocketWSGIHandler(WebSocketHandler):
            def upgrade_websocket(self):
                """Override to add wallet verification."""
                if self.environ.get('HTTP_UPGRADE', '').lower() == 'websocket':
                    # Extract wallet
                    path = self.environ.get('PATH_INFO', '')
                    query = self.environ.get('QUERY_STRING', '')
                    query_params = parse_qs(query)
                    wallet_address = query_params.get('wallet', [None])[0]
                    
                    if not wallet_address:
                        wallet_address = self.environ.get('HTTP_X_WALLET_ADDRESS')
                    
                    if not wallet_address or not validate_wallet_address(wallet_address.strip()):
                        self.start_response('403 Forbidden', [])
                        return None
                    
                    if not has_axgt_balance(wallet_address.strip()):
                        self.start_response('403 Forbidden', [])
                        return None
                    
                    logger.info(f"WebSocket upgrade approved: {mask_wallet_address(wallet_address.strip())}")
                
                return super().upgrade_websocket()
        
        # For now, use simple approach: Flask for HTTP, separate WS server
        # We'll run Flask on the main port and handle WS separately
        # Actually, let's use a simpler approach: run websockify on 6081 internally
        # and have Flask redirect/proxy WS connections after verification
        
        logger.info("Starting HTTP server (WebSocket handled separately)")
        app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
        
    except ImportError:
        logger.warning("gevent-websocket not available, using basic Flask server")
        app.run(host=host, port=port, debug=False, use_reloader=False)

if __name__ == '__main__':
    run_server()
