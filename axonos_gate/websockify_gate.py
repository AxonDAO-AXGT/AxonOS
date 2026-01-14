#!/usr/bin/env python3
"""
Websockify Gate Wrapper

Wraps websockify to add AXGT wallet verification.
This script is called by supervisord instead of websockify directly.
"""

import os
import sys
import logging
import json
from urllib.parse import parse_qs, urlparse

# Local security helpers (same directory)
from security_utils import cors_origin_for_request, get_rate_limiter_from_env, parse_cors_allowlist

# Add system Python path for Debian packages (websockify) FIRST
if '/usr/lib/python3/dist-packages' not in sys.path:
    sys.path.insert(0, '/usr/lib/python3/dist-packages')

# Import websockify early
try:
    import websockify
    # Check if WebSocketProxy is available
    if not hasattr(websockify, 'WebSocketProxy'):
        # Try importing from websockifyserver
        from websockify import websockifyserver
        websockify.WebSocketProxy = websockifyserver.WebSocketProxy
except (ImportError, AttributeError) as e:
    # Can't use logger yet, print to stderr
    print(f"ERROR: websockify not available: {e}. Install with: apt install python3-websockify", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Add parent directory to path for imports
_script_dir = os.path.dirname(os.path.abspath(__file__))
if '/axonos_gate' not in sys.path:
    sys.path.insert(0, '/axonos_gate')

# Import our modules
try:
    from axgt_verifier import has_access, validate_wallet_address, mask_wallet_address
except ImportError:
    # Fallback to package import
    try:
        from axonos_gate.axgt_verifier import has_axgt_balance, validate_wallet_address, mask_wallet_address
    except ImportError as e:
        print(f"ERROR: Cannot import axgt_verifier: {e}", file=sys.stderr)
        sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

_allow_any, _allowlist = parse_cors_allowlist(os.getenv("AXGT_CORS_ORIGINS"))
_rate_limiter = get_rate_limiter_from_env()

def _extract_wallet_from_path_and_headers(path: str, headers) -> str | None:
    """Extract wallet address from query string (?wallet=0x...) or header X-Wallet-Address."""
    try:
        parsed = urlparse(path if path else '/')
        query_params = parse_qs(parsed.query)
        wallet_address = query_params.get('wallet', [None])[0]
    except Exception:
        wallet_address = None

    if not wallet_address:
        # headers is an email.message.Message-like object in BaseHTTPRequestHandler
        wallet_address = headers.get('X-Wallet-Address') if headers else None

    if not wallet_address:
        return None

    return wallet_address.strip()


class AxonOSProxyRequestHandler(websockify.websocketproxy.ProxyRequestHandler):
    """
    Extends websockify's HTTP handler to:
    - Serve /api/auth/verify-wallet on the SAME origin/port as noVNC (6080)
    - Gate WebSocket upgrades using the wallet (AXGT balance OR 7-day trial)
    """

    def _send_json(self, status_code: int, payload: dict):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        # CORS: default is same-origin (no wildcard). For unusual deployments set AXGT_CORS_ORIGINS.
        origin = cors_origin_for_request(
            self.headers.get("Origin"),
            self.headers.get("Host"),
            _allow_any,
            _allowlist,
        )
        if origin:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Wallet-Address')
            self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        if self.path.startswith('/api/auth/verify-wallet'):
            self.send_response(200)
            origin = cors_origin_for_request(
                self.headers.get("Origin"),
                self.headers.get("Host"),
                _allow_any,
                _allowlist,
            )
            if origin:
                self.send_header('Access-Control-Allow-Origin', origin)
                self.send_header('Vary', 'Origin')
                self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Wallet-Address')
                self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        return super().do_OPTIONS()

    def do_POST(self):
        if not self.path.startswith('/api/auth/verify-wallet'):
            # websockify doesn't implement POST for static; return 404 for safety
            return self.send_error(404, "Not Found")

        # Best-effort rate limiting (per client IP)
        if _rate_limiter is not None:
            client_ip = (self.headers.get("X-Forwarded-For") or self.client_address[0] or "unknown").split(",")[0].strip()
            if not _rate_limiter.allow(client_ip):
                return self._send_json(429, {"verified": False, "error": "Rate limit exceeded"})

        try:
            content_length = int(self.headers.get('Content-Length') or '0')
        except ValueError:
            content_length = 0

        raw = self.rfile.read(content_length) if content_length > 0 else b''
        try:
            data = json.loads(raw.decode('utf-8') or '{}')
        except Exception:
            return self._send_json(400, {'verified': False, 'error': 'Invalid JSON'})

        wallet_address = (data.get('wallet_address') or '').strip()
        if not wallet_address:
            return self._send_json(400, {'verified': False, 'error': 'wallet_address is required'})

        if not validate_wallet_address(wallet_address):
            return self._send_json(400, {
                'verified': False,
                'error': 'Invalid wallet address format. Must be 0x followed by 40 hex characters.'
            })

        access_granted, access_type, days_remaining = has_access(wallet_address)
        if not access_granted:
            logger.info(f"Wallet verification failed: {mask_wallet_address(wallet_address)}")
            return self._send_json(200, {'verified': False, 'error': 'No access available for this wallet'})

        resp = {'verified': True, 'access_type': access_type}
        if access_type == 'trial' and days_remaining is not None:
            resp['trial_days_remaining'] = round(days_remaining, 1)
            resp['message'] = f'7-day trial active ({days_remaining:.1f} days remaining)'
        elif access_type == 'balance':
            resp['message'] = 'Wallet verified - AXGT holder'

        logger.info(f"Wallet verified: {mask_wallet_address(wallet_address)} (access_type: {access_type})")
        return self._send_json(200, resp)

    def handle_upgrade(self):
        # Gate WebSocket upgrades. If wallet is missing/invalid/unverified -> 403 and do not upgrade.
        wallet_address = _extract_wallet_from_path_and_headers(self.path, self.headers)
        if not wallet_address:
            self.send_error(403, "Wallet address required (?wallet=0x... or X-Wallet-Address)")
            return

        if not validate_wallet_address(wallet_address):
            self.send_error(403, "Invalid wallet address format")
            return

        access_granted, access_type, days_remaining = has_access(wallet_address)
        if not access_granted:
            self.send_error(403, "Wallet does not hold AXGT and trial is not active")
            return

        logger.info(f"WebSocket upgrade approved ({access_type}): {mask_wallet_address(wallet_address)}")
        return super().handle_upgrade()

def main():
    """Run websockify server with wallet gating + same-origin /api/auth/verify-wallet."""
    # Get configuration
    listen_port = int(os.getenv('WEBSOCKIFY_PORT', '6080'))
    target_host = os.getenv('VNC_HOST', 'localhost')
    target_port = int(os.getenv('VNC_PORT', '5901'))
    web_dir = os.getenv('NOVNC_WEB_DIR', '/usr/share/novnc')
    
    logger.info(f"Starting Websockify on port {listen_port}")
    logger.info(f"Target: {target_host}:{target_port}")
    logger.info("AXGT gate enabled: /api/auth/verify-wallet served on same origin; WebSocket upgrades require wallet")
    
    # Create and run the proxy
    server = websockify.WebSocketProxy(
        RequestHandlerClass=AxonOSProxyRequestHandler,
        listen_port=listen_port,
        target_host=target_host,
        target_port=target_port,
        web=web_dir
    )
    
    server.start_server()

if __name__ == '__main__':
    main()
