#!/bin/bash
# Build, run AxonOS (GPU, noVNC only), install cloudflared in-container, then start a Cloudflare Tunnel to noVNC.
# For quick online testing. Requires: .env, AXONOS_VNC_PASSWORD (or pass password as first arg).
# Tunnel runs in foreground; Ctrl+C stops the tunnel (container keeps running).

set -e

PASSWORD="${1:-$AXONOS_VNC_PASSWORD}"
if [ -z "$PASSWORD" ]; then
  echo "Usage: $0 <password>   # or set AXONOS_VNC_PASSWORD"
  exit 1
fi

IMAGE_TAG="${2:-axonos:latest}"
CONTAINER_NAME="axonos"

echo "Building image: $IMAGE_TAG"
docker build --build-arg PASSWORD="$PASSWORD" -t "$IMAGE_TAG" .

docker rm -f "$CONTAINER_NAME" 2>/dev/null || true
echo "Starting container (GPU, noVNC on 6080)..."
docker run -d --gpus all --rm --env-file .env -p 6080:6080 --name "$CONTAINER_NAME" "$IMAGE_TAG"

echo "Installing cloudflared in container..."
docker exec "$CONTAINER_NAME" bash -lc 'wget -q -O /tmp/cloudflared-linux-amd64.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb && (dpkg -i /tmp/cloudflared-linux-amd64.deb || apt-get -f install -y)'

echo "Starting Cloudflare Tunnel (foreground). Ctrl+C to stop tunnel."
docker exec -it "$CONTAINER_NAME" cloudflared tunnel --url http://localhost:6080
