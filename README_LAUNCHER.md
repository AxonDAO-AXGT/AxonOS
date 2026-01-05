# AxonOS Launcher

Command-line and GUI launcher for building and deploying AxonOS.

## CLI Mode (Default - For Headless GPU Servers)

The launcher defaults to CLI mode, perfect for headless GPU servers without GUI support.

### Quick Start

```bash
# List available applications
axonos list

# Build image
axonos build --password your_secure_password

# Deploy with GPU support
axonos deploy --gpu
```

### Full Workflow

```bash
# 1. List applications
axonos list

# 2. Generate custom Dockerfile (optional)
axonos generate

# 3. Build image
axonos build --password secure_password

# 4. Deploy with GPU
axonos deploy --gpu

# Access at: http://your-server:6080/vnc.html
```

## GUI Mode (Optional)

For systems with display support, GUI mode is available:

```bash
axonos --gui
```

## Commands

See `axonos_launcher/README_CLI.md` for complete CLI documentation.

## Installation

The launcher is included in the AxonOS repository. No separate installation needed.

```bash
# From AxonOS root directory
python3 axonos_launcher/cli.py list
# or
python3 axonos_launcher/main.py list
```

## Headless Server Deployment

Perfect for GPU servers without GUI:

1. SSH into your GPU server
2. Clone AxonOS repository
3. Use CLI commands to build and deploy
4. Access via web browser from any machine

No X11, no display server required!
