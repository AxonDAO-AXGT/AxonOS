# CLI Launcher Conversion

## Overview

Converted AxonOS Launcher from GUI-only to CLI-first, designed for headless GPU servers.

## Changes Made

### 1. New CLI Interface
- **File**: `axonos_launcher/cli.py`
- **Purpose**: Command-line interface for headless servers
- **Features**:
  - List applications
  - Generate Dockerfiles
  - Build Docker images
  - Deploy containers
  - Configuration management

### 2. Core Logic Extraction
- **File**: `axonos_launcher/launcher_core.py`
- **Purpose**: Shared business logic without GUI dependencies
- **Benefits**: 
  - Reusable by both CLI and GUI
  - No tkinter dependencies
  - Works on headless servers

### 3. Main Entry Point Update
- **File**: `axonos_launcher/main.py`
- **Change**: Defaults to CLI mode, GUI available with `--gui` flag
- **Behavior**:
  - `axonos list` → CLI mode (default)
  - `axonos --gui` → GUI mode (requires display)

## CLI Commands

```bash
# List applications
axonos list

# Generate Dockerfile
axonos generate

# Build image
axonos build --password "$AXONOS_VNC_PASSWORD"

# Deploy container
axonos deploy --gpu

# Configuration management
axonos config save --file config.json
axonos config load --file config.json
```

## Remaining Folders

The following `descios_*` folders remain:
- `build/descios_launcher/` - Build artifacts (can be cleaned)
- `build/descios_launcher_linux/` - Build artifacts (can be cleaned)

These are build outputs and don't affect functionality. They can be safely removed or will be regenerated with new names on next build.

## Migration Notes

- **GUI users**: Use `axonos --gui` to access GUI mode
- **CLI users**: Use `axonos <command>` directly (CLI is default)
- **Headless servers**: CLI mode works without X11/display
- **Configuration**: Config files are JSON format, compatible between CLI and GUI

## Testing

CLI has been tested and verified:
- ✅ List command works
- ✅ Generate command works
- ✅ Help system works
- ✅ Version display works
- ✅ Core launcher initializes correctly
