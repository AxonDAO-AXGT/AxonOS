# AXGT Holding-Credit Migration Checklist

- [x] Add global per-wallet usage ledger with persistence and locking.
- [x] Implement holding-credit policy with `remaining_minutes` in verifier responses.
- [x] Add lock/warning-capable verify + wallet-status endpoints and WebSocket enforcement.
- [x] Add 10-minute warning + lock overlay with periodic wallet-status polling in VNC UI.
- [x] Harden sign-to-verify with one-time wallet-bound challenges.
- [x] Move websocket auth token transport to HttpOnly cookie (remove URL token usage).
- [x] Require auth token for wallet-status to block unauthenticated usage draining.
- [x] Reduce token-race disconnects with near-expiry rotation + short grace overlap.
- [ ] Run lint and smoke validation for lockout, warning, and unlock recovery scenarios.
