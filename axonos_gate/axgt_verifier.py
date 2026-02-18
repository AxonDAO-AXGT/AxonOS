#!/usr/bin/env python3
"""
AXGT Wallet Verification Module

Checks hold-based access and off-chain usage credits for AXGT wallets.
"""

import os
import re
import logging
import time
import json
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from threading import Lock
from typing import Optional, Tuple, Dict, Any
import requests

logger = logging.getLogger(__name__)

# ERC-20 balanceOf function signature hash (first 4 bytes of keccak256)
BALANCE_OF_SIGNATURE = "0x70a08231"
# ERC-20 decimals() function signature hash.
DECIMALS_SIGNATURE = "0x313ce567"
DEFAULT_AXGT_MIN_HOLD = Decimal("100")
DEFAULT_TOKEN_DECIMALS = 18
DEFAULT_CREDIT_PER_100_AXGT_MINUTES = 60
DEFAULT_WARNING_THRESHOLD_MINUTES = 10
_USAGE_DB_PATH_DEFAULT = "/var/lib/axonos_gate/usage.json"
_USAGE_RETENTION_DAYS_DEFAULT = 180
_HUNDRED_AXGT = Decimal("100")

_usage_registry: Dict[str, Dict[str, float]] = {}
_usage_lock = Lock()
_usage_db_loaded = False

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

# Sign-to-verify: EIP-191 personal_sign challenge (minute-grained, no server state)
_CHALLENGE_PREFIX = "AxonOS verify\n"
_CHALLENGE_VALID_WINDOW_MINUTES = 2


def get_challenge_message() -> str:
    """Return a time-based challenge string for the client to sign (minute granularity)."""
    minute_ts = int(time.time() // 60)
    return _CHALLENGE_PREFIX + str(minute_ts)


def is_challenge_message_recent(message: str) -> bool:
    """Return True if message is our challenge format and within the allowed time window."""
    if not message or not message.startswith(_CHALLENGE_PREFIX):
        return False
    try:
        minute_ts = int(message[len(_CHALLENGE_PREFIX) :].strip())
    except ValueError:
        return False
    now_minute = int(time.time() // 60)
    return 0 <= (now_minute - minute_ts) <= _CHALLENGE_VALID_WINDOW_MINUTES


def recover_signer_from_signature(message: str, signature_hex: str) -> Optional[str]:
    """
    Recover Ethereum address from EIP-191 personal_sign(message, signature).
    Returns normalized 0x-prefixed address or None on failure.
    """
    if not message or not signature_hex:
        return None
    sig = (signature_hex.strip() or "").lower()
    if not sig.startswith("0x"):
        sig = "0x" + sig
    # EIP-191 personal_sign: 65 bytes (r,s,v) = 130 hex chars; some wallets use 131
    if len(sig) < 132 or len(sig) > 134:
        return None
    try:
        from eth_account import Account
        from eth_account.messages import encode_defunct
        recovered = Account.recover_message(encode_defunct(text=message), signature=sig)
        return recovered if recovered else None
    except Exception as e:
        logger.warning("Signature recovery failed: %s", e)
        return None


def verify_signed_challenge(
    wallet_address: str, message: str, signature_hex: str
) -> bool:
    """
    Return True if message is a recent challenge and signature recovers to wallet_address.
    """
    if not validate_wallet_address(wallet_address):
        return False
    if not is_challenge_message_recent(message):
        return False
    recovered = recover_signer_from_signature(message, signature_hex)
    if not recovered:
        return False
    return recovered.lower() == wallet_address.lower()


def _usage_db_path() -> str:
    return os.getenv("AXGT_USAGE_DB_PATH", _USAGE_DB_PATH_DEFAULT)

def _usage_retention_days() -> int:
    raw = (os.getenv("AXGT_USAGE_RETENTION_DAYS") or "").strip()
    if not raw:
        return _USAGE_RETENTION_DAYS_DEFAULT
    try:
        days = int(raw)
        if days <= 0:
            raise ValueError("must be positive")
        return days
    except ValueError:
        logger.warning(
            "Invalid AXGT_USAGE_RETENTION_DAYS value '%s'; using default %s",
            raw,
            _USAGE_RETENTION_DAYS_DEFAULT,
        )
        return _USAGE_RETENTION_DAYS_DEFAULT

def _ensure_usage_db_loaded() -> None:
    global _usage_db_loaded
    if _usage_db_loaded:
        return
    path = _usage_db_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            if isinstance(data, dict):
                for wallet, record in data.items():
                    if not isinstance(wallet, str) or not isinstance(record, dict):
                        continue
                    consumed = record.get("consumed_minutes")
                    last_update = record.get("last_update_ts")
                    if isinstance(consumed, (int, float)) and isinstance(last_update, (int, float)):
                        _usage_registry[wallet.lower()] = {
                            "consumed_minutes": float(max(0.0, consumed)),
                            "last_update_ts": float(last_update),
                        }
    except Exception as e:
        logger.warning("Failed to load usage registry from disk: %s", e)
    finally:
        _usage_db_loaded = True

def _persist_usage_best_effort() -> None:
    path = _usage_db_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_usage_registry, f)
        os.replace(tmp, path)
    except Exception as e:
        logger.warning("Failed to persist usage registry to disk: %s", e)

def _cleanup_usage_registry(now_ts: float) -> None:
    retention_seconds = _usage_retention_days() * 86400
    if retention_seconds <= 0:
        return
    stale_wallets = [
        wallet
        for wallet, record in _usage_registry.items()
        if (now_ts - float(record.get("last_update_ts", now_ts))) > retention_seconds
    ]
    for wallet in stale_wallets:
        _usage_registry.pop(wallet, None)

def _eth_call(rpc_url: str, contract_address: str, data: str) -> Optional[str]:
    """Run a single eth_call and return the hex result string."""
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
    response = requests.post(
        rpc_url,
        json=payload,
        timeout=10,
        headers={"Content-Type": "application/json"}
    )
    response.raise_for_status()
    result = response.json()
    if 'error' in result:
        logger.error(f"RPC eth_call error: {result['error']}")
        return None
    if 'result' not in result:
        logger.error("No result in eth_call RPC response")
        return None
    return result['result']

def _get_min_hold_amount() -> Decimal:
    """Read AXGT_MIN_HOLD_AMOUNT from env; fallback to default if invalid."""
    raw = (os.getenv("AXGT_MIN_HOLD_AMOUNT") or "").strip()
    if not raw:
        return DEFAULT_AXGT_MIN_HOLD
    try:
        parsed = Decimal(raw)
        if parsed < 0:
            raise InvalidOperation("negative not allowed")
        return parsed
    except (InvalidOperation, ValueError):
        logger.warning(
            "Invalid AXGT_MIN_HOLD_AMOUNT value '%s'; using default %s",
            raw,
            str(DEFAULT_AXGT_MIN_HOLD)
        )
        return DEFAULT_AXGT_MIN_HOLD

def _get_credit_per_100_axgt_minutes() -> int:
    raw = (os.getenv("AXGT_CREDIT_PER_100_AXGT_MINUTES") or "").strip()
    if not raw:
        return DEFAULT_CREDIT_PER_100_AXGT_MINUTES
    try:
        minutes = int(raw)
        if minutes <= 0:
            raise ValueError("must be positive")
        return minutes
    except ValueError:
        logger.warning(
            "Invalid AXGT_CREDIT_PER_100_AXGT_MINUTES value '%s'; using default %s",
            raw,
            DEFAULT_CREDIT_PER_100_AXGT_MINUTES,
        )
        return DEFAULT_CREDIT_PER_100_AXGT_MINUTES

def _get_warning_threshold_minutes() -> int:
    raw = (os.getenv("AXGT_WARNING_THRESHOLD_MINUTES") or "").strip()
    if not raw:
        return DEFAULT_WARNING_THRESHOLD_MINUTES
    try:
        minutes = int(raw)
        if minutes <= 0:
            raise ValueError("must be positive")
        return minutes
    except ValueError:
        logger.warning(
            "Invalid AXGT_WARNING_THRESHOLD_MINUTES value '%s'; using default %s",
            raw,
            DEFAULT_WARNING_THRESHOLD_MINUTES,
        )
        return DEFAULT_WARNING_THRESHOLD_MINUTES

def get_min_hold_amount_display() -> str:
    """Return a friendly string representation of AXGT minimum hold amount."""
    amount = _get_min_hold_amount()
    normalized = format(amount.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized or "0"

def _decimal_display(value: Decimal) -> str:
    normalized = format(value.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized or "0"

def get_credit_policy() -> Dict[str, Any]:
    return {
        "min_hold_amount": get_min_hold_amount_display(),
        "credit_per_100_axgt_minutes": _get_credit_per_100_axgt_minutes(),
        "warning_threshold_minutes": _get_warning_threshold_minutes(),
    }

def _get_token_decimals(contract_address: str, rpc_url: str) -> int:
    """
    Fetch ERC-20 decimals from chain; fallback to DEFAULT_TOKEN_DECIMALS.
    """
    try:
        decimals_hex = _eth_call(rpc_url, contract_address, DECIMALS_SIGNATURE)
        if not decimals_hex or decimals_hex == "0x":
            raise ValueError("empty decimals result")
        decimals = int(decimals_hex, 16)
        if decimals < 0 or decimals > 255:
            raise ValueError(f"invalid decimals value: {decimals}")
        return decimals
    except Exception as e:
        logger.warning(
            "Failed to read token decimals for AXGT contract %s: %s. Using default decimals=%s",
            contract_address,
            e,
            DEFAULT_TOKEN_DECIMALS,
        )
        return DEFAULT_TOKEN_DECIMALS

def _required_balance_base_units(decimals: int) -> int:
    """Convert configured AXGT_MIN_HOLD_AMOUNT to token base units."""
    min_hold_amount = _get_min_hold_amount()
    base_multiplier = Decimal(10) ** decimals
    required_units_decimal = (min_hold_amount * base_multiplier).to_integral_value(rounding=ROUND_CEILING)
    return int(required_units_decimal)

def _get_axgt_balance_info(wallet_address: str) -> Optional[Dict[str, Any]]:
    """Return AXGT balance details or None on failure."""
    if not validate_wallet_address(wallet_address):
        logger.warning("Invalid wallet address format: %s", mask_wallet_address(wallet_address))
        return None

    contract_address = (os.getenv('AXGT_CONTRACT_ADDRESS') or '').strip()
    rpc_url = (os.getenv('AXGT_RPC_URL') or '').strip()
    chain_id = (os.getenv('AXGT_CHAIN_ID') or '').strip()
    if not contract_address or not rpc_url or not chain_id:
        logger.error(
            "AXGT verification not configured. Set AXGT_CONTRACT_ADDRESS, AXGT_RPC_URL, and AXGT_CHAIN_ID."
        )
        return None

    expected_contract = (os.getenv('AXGT_EXPECTED_CONTRACT_ADDRESS') or '').strip()
    if expected_contract and contract_address.lower() != expected_contract.lower():
        logger.error("Contract address mismatch. Expected: %s, Got: %s", expected_contract, contract_address)
        return None

    try:
        padded_address = wallet_address[2:].lower().zfill(64)
        data = BALANCE_OF_SIGNATURE + padded_address
        balance_hex = _eth_call(rpc_url, contract_address, data)
        if not balance_hex or balance_hex == "0x":
            logger.warning("Empty balance result from RPC for %s", mask_wallet_address(wallet_address))
            return None
        balance_base_units = int(balance_hex, 16)
        decimals = _get_token_decimals(contract_address, rpc_url)
        divisor = Decimal(10) ** decimals
        balance_axgt = Decimal(balance_base_units) / divisor
        return {
            "contract_address": contract_address,
            "balance_base_units": balance_base_units,
            "decimals": decimals,
            "balance_axgt": balance_axgt,
        }
    except requests.exceptions.RequestException as e:
        logger.error("RPC request failed for %s: %s", mask_wallet_address(wallet_address), e)
        return None
    except (ValueError, KeyError) as e:
        logger.error("Error parsing balance response for %s: %s", mask_wallet_address(wallet_address), e)
        return None
    except Exception as e:
        logger.error("Unexpected error checking balance for %s: %s", mask_wallet_address(wallet_address), e)
        return None

def has_axgt_balance(wallet_address: str) -> bool:
    """
    Check if wallet holds AXGT tokens.
    
    Args:
        wallet_address: Ethereum wallet address (0x...)
        
    Returns:
        True if balance is >= AXGT_MIN_HOLD_AMOUNT, False otherwise
    """
    details = _get_axgt_balance_info(wallet_address)
    if not details:
        return False
    min_hold_amount = _get_min_hold_amount()
    return details["balance_axgt"] >= min_hold_amount

def get_wallet_access_status(wallet_address: str) -> Dict[str, Any]:
    """
    Evaluate hold + off-chain usage-credit status for a wallet.
    """
    warning_threshold = _get_warning_threshold_minutes()
    min_hold_amount = _get_min_hold_amount()
    base_response: Dict[str, Any] = {
        "verified": False,
        "access_type": None,
        "locked": True,
        "reason": "Wallet verification failed.",
        "remaining_minutes": 0.0,
        "consumed_minutes": 0.0,
        "capacity_minutes": 0.0,
        "warning_threshold_minutes": warning_threshold,
        "min_hold_amount": get_min_hold_amount_display(),
        "credit_per_100_axgt_minutes": _get_credit_per_100_axgt_minutes(),
        "balance_axgt": "0",
    }

    if not validate_wallet_address(wallet_address):
        base_response["reason"] = "Invalid wallet address format."
        return base_response

    details = _get_axgt_balance_info(wallet_address)
    if not details:
        base_response["reason"] = "Unable to verify AXGT balance."
        return base_response

    balance_axgt: Decimal = details["balance_axgt"]
    balance_display = _decimal_display(balance_axgt)
    base_response["balance_axgt"] = balance_display

    if balance_axgt < min_hold_amount:
        base_response["reason"] = f"Access requires holding at least {get_min_hold_amount_display()} AXGT."
        return base_response

    credit_per_100 = _get_credit_per_100_axgt_minutes()
    bucket_count = int(balance_axgt // _HUNDRED_AXGT)
    capacity_minutes = float(bucket_count * credit_per_100)
    now_ts = time.time()

    with _usage_lock:
        _ensure_usage_db_loaded()
        _cleanup_usage_registry(now_ts)
        wallet_key = wallet_address.lower()
        record = _usage_registry.get(wallet_key)
        if record is None:
            record = {
                "consumed_minutes": 0.0,
                "last_update_ts": now_ts,
            }
            _usage_registry[wallet_key] = record
        else:
            last_update_ts = float(record.get("last_update_ts", now_ts))
            elapsed_minutes = max(0.0, now_ts - last_update_ts) / 60.0
            record["consumed_minutes"] = float(record.get("consumed_minutes", 0.0)) + elapsed_minutes
            record["last_update_ts"] = now_ts
        consumed_minutes = float(record.get("consumed_minutes", 0.0))
        _persist_usage_best_effort()

    remaining_minutes = max(0.0, capacity_minutes - consumed_minutes)
    locked = remaining_minutes <= 0.0

    response: Dict[str, Any] = {
        "verified": not locked,
        "access_type": "holding_credit" if not locked else None,
        "locked": locked,
        "reason": None,
        "remaining_minutes": round(remaining_minutes, 2),
        "consumed_minutes": round(consumed_minutes, 2),
        "capacity_minutes": round(capacity_minutes, 2),
        "warning_threshold_minutes": warning_threshold,
        "min_hold_amount": get_min_hold_amount_display(),
        "credit_per_100_axgt_minutes": credit_per_100,
        "balance_axgt": balance_display,
    }
    if locked:
        response["reason"] = (
            "Usage credit exhausted. Increase held AXGT to raise capacity and unlock access."
        )
    elif remaining_minutes <= warning_threshold:
        response["reason"] = (
            f"Warning: less than {warning_threshold} minutes of AXGT usage credit remaining."
        )
    return response

def has_access(wallet_address: str) -> Tuple[bool, Optional[str], Optional[float]]:
    """
    Check if wallet has access based on AXGT minimum hold policy.
    
    Args:
        wallet_address: Ethereum wallet address (0x...)
        
    Returns:
        Tuple of (has_access, access_type, days_remaining)
        access_type: 'balance' if minimum hold is met, None otherwise
        days_remaining: unused (always None in hold-based policy)
    """
    if not validate_wallet_address(wallet_address):
        return False, None, None
    
    status = get_wallet_access_status(wallet_address)
    if status["verified"]:
        logger.info("Wallet %s has holding-credit access", mask_wallet_address(wallet_address))
        return True, status.get("access_type"), status.get("remaining_minutes")

    logger.info(
        "Wallet %s denied holding-credit access: %s",
        mask_wallet_address(wallet_address),
        status.get("reason"),
    )
    return False, None, status.get("remaining_minutes")
