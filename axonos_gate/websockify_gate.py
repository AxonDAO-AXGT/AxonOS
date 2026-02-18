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
import time
import secrets
from http.cookies import SimpleCookie
from threading import Lock
from urllib.parse import parse_qs, urlparse

# Local security helpers (same directory)
from security_utils import cors_origin_for_request, get_rate_limiter_from_env, parse_cors_allowlist

# Add system Python path for Ubuntu 22.04 packages (websockify) FIRST
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
    from axgt_verifier import (
        get_wallet_access_status,
        validate_wallet_address,
        mask_wallet_address,
        get_credit_policy,
        get_challenge_message,
        get_challenge_ttl_seconds,
        verify_signed_challenge,
    )
except ImportError:
    # Fallback to package import
    try:
        from axonos_gate.axgt_verifier import (
            get_wallet_access_status,
            validate_wallet_address,
            mask_wallet_address,
            get_credit_policy,
            get_challenge_message,
            get_challenge_ttl_seconds,
            verify_signed_challenge,
        )
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
_auth_lock = Lock()
_auth_tokens: dict[str, dict] = {}


def _auth_ttl_seconds() -> int:
    raw = (os.getenv("AXGT_AUTH_TOKEN_TTL_SECONDS") or "").strip()
    if not raw:
        return 300
    try:
        value = int(raw)
        if value <= 0:
            raise ValueError("must be positive")
        return value
    except ValueError:
        logger.warning("Invalid AXGT_AUTH_TOKEN_TTL_SECONDS '%s', using default 300", raw)
        return 300


def _auth_cookie_name() -> str:
    raw = (os.getenv("AXGT_AUTH_COOKIE_NAME") or "").strip()
    return raw or "axgt_auth_token"


def _auth_cookie_secure() -> bool:
    raw = (os.getenv("AXGT_AUTH_COOKIE_SECURE") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _build_auth_cookie(token: str | None, ttl_seconds: int) -> str:
    name = _auth_cookie_name()
    max_age = max(0, int(ttl_seconds))
    value = token or ""
    cookie = f"{name}={value}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Strict"
    if _auth_cookie_secure():
        cookie += "; Secure"
    return cookie


def _clear_auth_cookie() -> str:
    return _build_auth_cookie(None, 0)


def _prune_expired_auth_tokens(now_ts: float) -> None:
    expired = [
        token
        for token, record in _auth_tokens.items()
        if float(record.get("expires_at", 0)) <= now_ts
    ]
    for token in expired:
        _auth_tokens.pop(token, None)


def _revoke_wallet_tokens(wallet_address: str) -> None:
    wallet = wallet_address.lower()
    to_remove = [
        token
        for token, record in _auth_tokens.items()
        if record.get("wallet_address") == wallet
    ]
    for token in to_remove:
        _auth_tokens.pop(token, None)


def _issue_auth_token(wallet_address: str) -> tuple[str, int]:
    ttl = _auth_ttl_seconds()
    now_ts = time.time()
    token = secrets.token_urlsafe(32)
    with _auth_lock:
        _prune_expired_auth_tokens(now_ts)
        # Keep a single active token per wallet to reduce replay surface.
        _revoke_wallet_tokens(wallet_address)
        _auth_tokens[token] = {
            "wallet_address": wallet_address.lower(),
            "expires_at": now_ts + ttl,
        }
    return token, ttl


def _is_auth_token_valid(token: str, wallet_address: str) -> bool:
    now_ts = time.time()
    with _auth_lock:
        _prune_expired_auth_tokens(now_ts)
        record = _auth_tokens.get(token)
        if not record:
            return False
        if record.get("wallet_address") != wallet_address.lower():
            return False
        if float(record.get("expires_at", 0)) <= now_ts:
            _auth_tokens.pop(token, None)
            return False
        return True


def _rotate_auth_token(token: str, wallet_address: str) -> tuple[str, int] | tuple[None, None]:
    now_ts = time.time()
    ttl = _auth_ttl_seconds()
    with _auth_lock:
        _prune_expired_auth_tokens(now_ts)
        record = _auth_tokens.get(token)
        if not record:
            return None, None
        if record.get("wallet_address") != wallet_address.lower():
            return None, None
        if float(record.get("expires_at", 0)) <= now_ts:
            _auth_tokens.pop(token, None)
            return None, None
        _auth_tokens.pop(token, None)
        new_token = secrets.token_urlsafe(32)
        _auth_tokens[new_token] = {
            "wallet_address": wallet_address.lower(),
            "expires_at": now_ts + ttl,
        }
        return new_token, ttl

def _extract_wallet_from_path_and_headers(path: str, headers) -> str | None:
    """Extract wallet address from query string or header X-Wallet-Address."""
    try:
        parsed = urlparse(path if path else '/')
        query_params = parse_qs(parsed.query)
        wallet_address = query_params.get('wallet_address', [None])[0] or query_params.get('wallet', [None])[0]
    except Exception:
        wallet_address = None

    if not wallet_address:
        # headers is an email.message.Message-like object in BaseHTTPRequestHandler
        wallet_address = headers.get('X-Wallet-Address') if headers else None

    if not wallet_address:
        return None

    return wallet_address.strip()


def _extract_auth_token_from_path_and_headers(_path: str, headers) -> str | None:
    """Extract auth token from HttpOnly cookie or X-AXGT-Auth-Token header."""
    token = None
    if headers:
        cookie_raw = headers.get("Cookie")
        if cookie_raw:
            try:
                cookie = SimpleCookie()
                cookie.load(cookie_raw)
                morsel = cookie.get(_auth_cookie_name())
                if morsel:
                    token = morsel.value
            except Exception:
                token = None
    if not token and headers:
        token = headers.get('X-AXGT-Auth-Token')
    return token.strip() if token else None


class AxonOSProxyRequestHandler(websockify.websocketproxy.ProxyRequestHandler):
    """
    Extends websockify's HTTP handler to:
    - Serve /api/auth/verify-wallet on the SAME origin/port as noVNC (6080)
    - Gate WebSocket upgrades using wallet AXGT minimum-hold policy
    """

    def _send_json(self, status_code: int, payload: dict, set_cookie: str | None = None):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        if set_cookie:
            self.send_header('Set-Cookie', set_cookie)
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
            self.send_header('Access-Control-Allow-Credentials', 'true')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Wallet-Address, X-AXGT-Auth-Token')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        if (
            self.path.startswith('/api/auth/verify-wallet')
            or self.path.startswith('/api/auth/wallet-status')
            or self.path.startswith('/api/auth/challenge')
            or self.path.startswith('/api/config')
        ):
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
                self.send_header('Access-Control-Allow-Credentials', 'true')
                self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Wallet-Address, X-AXGT-Auth-Token')
                self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        return super().do_OPTIONS()

    def do_GET(self):
        # Serve a minimal config endpoint for UI display (no secrets).
        if self.path.startswith('/api/config'):
            contract = (os.getenv("AXGT_CONTRACT_ADDRESS") or "").strip()
            chain_id = (os.getenv("AXGT_CHAIN_ID") or "").strip()
            policy = get_credit_policy()
            payload = {
                "axgt_contract_address": contract or None,
                "axgt_chain_id": chain_id or None,
                "axgt_min_hold_amount": policy["min_hold_amount"],
                "axgt_credit_per_100_axgt_minutes": policy["credit_per_100_axgt_minutes"],
                "axgt_warning_threshold_minutes": policy["warning_threshold_minutes"],
            }
            return self._send_json(200, payload)
        if self.path.startswith('/api/auth/wallet-status'):
            wallet_address = _extract_wallet_from_path_and_headers(self.path, self.headers)
            if not wallet_address:
                return self._send_json(400, {'verified': False, 'error': 'wallet_address is required'})
            if not validate_wallet_address(wallet_address):
                return self._send_json(400, {
                    'verified': False,
                    'error': 'Invalid wallet address format. Must be 0x followed by 40 hex characters.'
                })
            auth_token = _extract_auth_token_from_path_and_headers(self.path, self.headers)
            if not auth_token:
                return self._send_json(401, {
                    'verified': False,
                    'error': 'AXGT auth token required. Please verify wallet again.'
                }, set_cookie=_clear_auth_cookie())
            if not _is_auth_token_valid(auth_token, wallet_address):
                return self._send_json(401, {
                    'verified': False,
                    'error': 'Invalid or expired AXGT auth token. Please verify wallet again.'
                }, set_cookie=_clear_auth_cookie())

            status = get_wallet_access_status(wallet_address, consume_usage=True)
            status['wallet_address'] = wallet_address
            if not status.get("verified"):
                status['error'] = status.get("reason") or 'Access denied for this wallet.'
                return self._send_json(200, status)
            # Sliding token rotation while session is healthy to reduce reconnect friction.
            new_token, ttl = _rotate_auth_token(auth_token, wallet_address)
            if not new_token:
                return self._send_json(401, {
                    'verified': False,
                    'error': 'AXGT auth token refresh failed. Please verify wallet again.'
                }, set_cookie=_clear_auth_cookie())
            status['auth_token'] = new_token
            status['auth_token_expires_in_seconds'] = ttl
            return self._send_json(200, status, set_cookie=_build_auth_cookie(new_token, ttl))
        if self.path.startswith('/api/auth/challenge'):
            wallet_address = _extract_wallet_from_path_and_headers(self.path, self.headers)
            if not wallet_address:
                return self._send_json(400, {'error': 'wallet_address is required'})
            if not validate_wallet_address(wallet_address):
                return self._send_json(400, {
                    'error': 'Invalid wallet address format. Must be 0x followed by 40 hex characters.'
                })
            try:
                payload = {
                    'challenge': get_challenge_message(wallet_address),
                    'challenge_expires_in_seconds': get_challenge_ttl_seconds(),
                }
                return self._send_json(200, payload)
            except ValueError:
                return self._send_json(400, {'error': 'Invalid wallet address format.'})
        return super().do_GET()

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

        message = (data.get('message') or '').strip()
        signature_hex = (data.get('signature') or '').strip()
        if not message or not signature_hex:
            return self._send_json(401, {
                'verified': False,
                'error': 'Signature required. Fetch /api/auth/challenge and sign it with this wallet.'
            })
        if not verify_signed_challenge(wallet_address, message, signature_hex):
            logger.info("Sign-to-verify failed for %s", mask_wallet_address(wallet_address))
            return self._send_json(401, {
                'verified': False,
                'error': 'Signature verification failed. Sign the challenge with the same wallet.'
            })

        status = get_wallet_access_status(wallet_address, consume_usage=False)
        if not status.get("verified"):
            logger.info(f"Wallet verification failed: {mask_wallet_address(wallet_address)}")
            status['error'] = status.get("reason") or 'Access denied for this wallet.'
            return self._send_json(200, status, set_cookie=_clear_auth_cookie())

        status['message'] = (
            f"Wallet verified - {status.get('remaining_minutes', 0)} minutes remaining"
        )
        logger.info(
            "Wallet verified: %s (remaining_minutes=%s)",
            mask_wallet_address(wallet_address),
            status.get("remaining_minutes"),
        )
        auth_token, ttl = _issue_auth_token(wallet_address)
        status['auth_token'] = auth_token
        status['auth_token_expires_in_seconds'] = ttl
        return self._send_json(200, status, set_cookie=_build_auth_cookie(auth_token, ttl))

    def handle_upgrade(self):
        # Gate WebSocket upgrades. If wallet is missing/invalid/unverified -> 403 and do not upgrade.
        wallet_address = _extract_wallet_from_path_and_headers(self.path, self.headers)
        if not wallet_address:
            self.send_error(403, "Wallet address required (?wallet=0x... or X-Wallet-Address)")
            return

        if not validate_wallet_address(wallet_address):
            self.send_error(403, "Invalid wallet address format")
            return

        auth_token = _extract_auth_token_from_path_and_headers(self.path, self.headers)
        if not auth_token:
            self.send_error(403, "AXGT auth token required")
            return
        if not _is_auth_token_valid(auth_token, wallet_address):
            self.send_error(403, "Invalid or expired AXGT auth token")
            return

        status = get_wallet_access_status(wallet_address, consume_usage=False)
        if not status.get("verified"):
            self.send_error(403, status.get("reason") or "Wallet is locked")
            return

        logger.info(
            "WebSocket upgrade approved (%s): %s",
            status.get("access_type"),
            mask_wallet_address(wallet_address),
        )
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
