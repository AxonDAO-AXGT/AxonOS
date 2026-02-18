# AXGT Holding-Credit Migration Checklist

- [x] Add global per-wallet usage ledger with persistence and locking.
- [x] Implement holding-credit policy with `remaining_minutes` in verifier responses.
- [x] Add lock/warning-capable verify + wallet-status endpoints and WebSocket enforcement.
- [x] Add 10-minute warning + lock overlay with periodic wallet-status polling in VNC UI.
- [ ] Run lint and smoke validation for lockout, warning, and unlock recovery scenarios.
