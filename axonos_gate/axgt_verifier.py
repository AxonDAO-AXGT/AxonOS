#!/usr/bin/env python3
"""
AXGT Wallet Verification Module

Checks if a wallet address holds AXGT tokens or has an active 7-day trial.
"""

import os
import re
import logging
import time
import json
from typing import Optional, Tuple, Dict
import requests
from threading import Lock

logger = logging.getLogger(__name__)

# Trial tracking (in-memory, per-process)
# In production, this should be stored in a database. For now we persist to disk
# to prevent trivial trial resets on container restart.
_trial_registry: Dict[str, float] = {}  # wallet_address (lowercase) -> trial_start_timestamp
_trial_lock = Lock()
TRIAL_DURATION_SECONDS = 7 * 24 * 60 * 60  # 7 days in seconds

# Persist trials to disk (best-effort). Use a path that is writable in-container.
_TRIAL_DB_PATH_DEFAULT = "/var/lib/axonos_gate/trials.json"
_trial_db_loaded = False

def _trial_db_path() -> str:
    return os.getenv("AXGT_TRIAL_DB_PATH", _TRIAL_DB_PATH_DEFAULT)

def _ensure_trial_db_loaded() -> None:
    """Load persisted trials once per process (best-effort)."""
    global _trial_db_loaded
    if _trial_db_loaded:
        return
    path = _trial_db_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            if isinstance(data, dict):
                # Only accept string->number mappings
                for k, v in data.items():
                    if isinstance(k, str) and isinstance(v, (int, float)):
                        _trial_registry[k.lower()] = float(v)
    except Exception as e:
        logger.warning(f"Failed to load trial registry from disk: {e}")
    finally:
        _trial_db_loaded = True

def _persist_trials_best_effort() -> None:
    """Persist current trial registry to disk (best-effort, atomic write)."""
    path = _trial_db_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_trial_registry, f)
        os.replace(tmp, path)
    except Exception as e:
        logger.warning(f"Failed to persist trial registry to disk: {e}")

# ERC-20 balanceOf function signature hash (first 4 bytes of keccak256)
BALANCE_OF_SIGNATURE = "0x70a08231"

def mask_wallet_address(address: str) -> str:
    """Mask wallet address for logging (show first 6 and last 4 chars)."""
    if not address or len(address) < 10:
        return "***"
    return f"{address[:6]}...{address[-4:]}"

def validate_wallet_address(address: str) -> bool:
    """Validate Ethereum wallet address format."""
    if not address:
        return False
    # Must start with 0x and have exactly 40 hex characters
    pattern = r'^0x[a-fA-F0-9]{40}$'
    return bool(re.match(pattern, address))

def start_trial(wallet_address: str) -> bool:
    """
    Start a 7-day trial for a wallet address.
    
    Args:
        wallet_address: Ethereum wallet address (0x...)
        
    Returns:
        True if trial started, False if already has trial or invalid address
    """
    if not validate_wallet_address(wallet_address):
        return False
    
    wallet_key = wallet_address.lower()
    
    with _trial_lock:
        _ensure_trial_db_loaded()
        # Check if trial already exists and is still valid
        if wallet_key in _trial_registry:
            trial_start = _trial_registry[wallet_key]
            elapsed = time.time() - trial_start
            if elapsed < TRIAL_DURATION_SECONDS:
                logger.info(f"Trial already active for {mask_wallet_address(wallet_address)} ({elapsed/86400:.1f} days remaining)")
                return False
        
        # Start new trial
        _trial_registry[wallet_key] = time.time()
        _persist_trials_best_effort()
        logger.info(f"Started 7-day trial for {mask_wallet_address(wallet_address)}")
        return True

def is_trial_active(wallet_address: str) -> Tuple[bool, Optional[float]]:
    """
    Check if wallet has an active trial.
    
    Args:
        wallet_address: Ethereum wallet address (0x...)
        
    Returns:
        Tuple of (is_active, days_remaining)
    """
    if not validate_wallet_address(wallet_address):
        return False, None
    
    wallet_key = wallet_address.lower()
    
    with _trial_lock:
        _ensure_trial_db_loaded()
        if wallet_key not in _trial_registry:
            return False, None
        
        trial_start = _trial_registry[wallet_key]
        elapsed = time.time() - trial_start
        days_remaining = (TRIAL_DURATION_SECONDS - elapsed) / 86400
        
        if elapsed < TRIAL_DURATION_SECONDS:
            return True, days_remaining
        else:
            # Trial expired, remove it
            del _trial_registry[wallet_key]
            _persist_trials_best_effort()
            return False, None

def has_axgt_balance(wallet_address: str) -> bool:
    """
    Check if wallet holds AXGT tokens.
    
    Args:
        wallet_address: Ethereum wallet address (0x...)
        
    Returns:
        True if balance > 0, False otherwise
    """
    # Validate address format
    if not validate_wallet_address(wallet_address):
        logger.warning(f"Invalid wallet address format: {mask_wallet_address(wallet_address)}")
        return False
    
    # Get configuration from environment (no hardcoded defaults)
    contract_address = (os.getenv('AXGT_CONTRACT_ADDRESS') or '').strip()
    rpc_url = (os.getenv('AXGT_RPC_URL') or '').strip()
    chain_id = (os.getenv('AXGT_CHAIN_ID') or '').strip()

    if not contract_address or not rpc_url or not chain_id:
        logger.error(
            "AXGT verification not configured. Set AXGT_CONTRACT_ADDRESS, AXGT_RPC_URL, and AXGT_CHAIN_ID."
        )
        return False

    # Optional safety check: if an expected contract is provided, enforce it.
    expected_contract = (os.getenv('AXGT_EXPECTED_CONTRACT_ADDRESS') or '').strip()
    if expected_contract and contract_address.lower() != expected_contract.lower():
        logger.error(f"Contract address mismatch. Expected: {expected_contract}, Got: {contract_address}")
        return False
    
    try:
        # Prepare the RPC call
        # balanceOf(address) -> uint256
        # Pad wallet address to 32 bytes (64 hex chars) for the data field
        padded_address = wallet_address[2:].lower().zfill(64)
        data = BALANCE_OF_SIGNATURE + padded_address
        
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_call",
            "params": [
                {
                    "to": contract_address,
                    "data": data
                },
                "latest"
            ],
            "id": 1
        }
        
        logger.info(f"Checking AXGT balance for {mask_wallet_address(wallet_address)}")
        
        # Make RPC call
        response = requests.post(
            rpc_url,
            json=payload,
            timeout=10,
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        
        result = response.json()
        
        if 'error' in result:
            logger.error(f"RPC error checking balance: {result['error']}")
            return False
        
        if 'result' not in result:
            logger.error("No result in RPC response")
            return False
        
        # Parse the result (hex string representing uint256)
        balance_hex = result['result']
        if balance_hex == '0x':
            logger.warning(f"Empty result from RPC for {mask_wallet_address(wallet_address)}")
            return False
        
        # Convert hex to integer
        balance = int(balance_hex, 16)
        
        logger.info(f"Balance check for {mask_wallet_address(wallet_address)}: {balance} (wei)")
        
        # Return True if balance > 0
        return balance > 0
        
    except requests.exceptions.RequestException as e:
        logger.error(f"RPC request failed for {mask_wallet_address(wallet_address)}: {e}")
        # Fail closed - if RPC is unavailable, deny access
        return False
    except (ValueError, KeyError) as e:
        logger.error(f"Error parsing RPC response for {mask_wallet_address(wallet_address)}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error checking balance for {mask_wallet_address(wallet_address)}: {e}")
        return False

def has_access(wallet_address: str) -> Tuple[bool, Optional[str], Optional[float]]:
    """
    Check if wallet has access (either has AXGT balance or active trial).
    
    Args:
        wallet_address: Ethereum wallet address (0x...)
        
    Returns:
        Tuple of (has_access, access_type, days_remaining)
        access_type: 'balance' if has AXGT, 'trial' if on trial, None if no access
        days_remaining: Only set for trial access
    """
    if not validate_wallet_address(wallet_address):
        return False, None, None
    
    # First check if wallet has AXGT balance
    if has_axgt_balance(wallet_address):
        logger.info(f"Wallet {mask_wallet_address(wallet_address)} has AXGT balance")
        return True, 'balance', None
    
    # Check if wallet has active trial
    trial_active, days_remaining = is_trial_active(wallet_address)
    if trial_active:
        logger.info(f"Wallet {mask_wallet_address(wallet_address)} has active trial ({days_remaining:.1f} days remaining)")
        return True, 'trial', days_remaining
    
    # No balance and no trial - start trial if this is first verification
    logger.info(f"Wallet {mask_wallet_address(wallet_address)} has no balance, starting trial")
    if start_trial(wallet_address):
        return True, 'trial', 7.0
    
    # Should not reach here, but fail closed
    return False, None, None
