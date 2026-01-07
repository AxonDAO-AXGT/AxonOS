#!/usr/bin/env python3
"""
WebSocket Gate Wrapper

Simple WebSocket server that gates connections and proxies to websockify.
"""

import os
import logging
import socket
import select
from urllib.parse import parse_qs, urlparse
import websocket
from websocket import WebSocketServerProtocol

from axonos_gate.axgt_verifier import has_axgt_balance, validate_wallet_address, mask_wallet_address

logger = logging.getLogger(__name__)

class WebSocketGateHandler:
    """WebSocket handler that gates connections and proxies to websockify."""
    
    def __init__(self, host='0.0.0.0', ws_port=6080, websockify_url='ws://localhost:6081/websockify'):
        self.host = host
        self.ws_port = ws_port
        self.websockify_url = websockify_url
    
    def verify_wallet(self, path, headers):
        """Extract and verify wallet address from request."""
        # Extract wallet from query string
        parsed = urlparse(path)
        query_params = parse_qs(parsed.query)
        wallet_address = query_params.get('wallet', [None])[0]
        
        # Also check headers
        if not wallet_address:
            wallet_address = headers.get('X-Wallet-Address') or headers.get('x-wallet-address')
        
        if not wallet_address:
            return None, "No wallet address provided"
        
        wallet_address = wallet_address.strip()
        
        # Validate format
        if not validate_wallet_address(wallet_address):
            return None, f"Invalid wallet format: {mask_wallet_address(wallet_address)}"
        
        # Check AXGT balance
        if not has_axgt_balance(wallet_address):
            return None, f"No AXGT balance: {mask_wallet_address(wallet_address)}"
        
        logger.info(f"Wallet verified: {mask_wallet_address(wallet_address)}")
        return wallet_address, None
    
    def run(self):
        """Run WebSocket gate server."""
        # For simplicity, we'll use a basic approach:
        # Run websockify on internal port, and this server will be a simple HTTP/WS proxy
        # Actually, let's use websockify's built-in capabilities by running it
        # and having Flask handle the gate check via a middleware approach.
        
        # Since websockify is complex to wrap, we'll use a simpler approach:
        # The Flask server will handle WebSocket upgrades using gevent-websocket
        # and proxy to websockify after verification.
        
        logger.info("WebSocket gate handler initialized (handled by Flask server)")
        # The actual WebSocket handling will be done in server.py using gevent-websocket
