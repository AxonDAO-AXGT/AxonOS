#!/bin/bash
# Build script for AxonOS Docker image
# This script builds the AxonOS image with proper configuration

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}🔨 AxonOS Docker Image Builder${NC}"
echo "=================================="
echo ""

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed or not in PATH${NC}"
    exit 1
fi

# Require explicit password input (used for both VNC auth and container user sudo password).
if [ -z "$1" ]; then
    echo -e "${RED}❌ No password provided.${NC}"
    echo "Usage: $0 <password> [image_tag]"
    echo "Example: $0 mySecurePassword123 axonos:latest"
    exit 1
fi

PASSWORD="$1"
IMAGE_TAG="${2:-axonos:latest}"

echo -e "${GREEN}Building AxonOS image: ${IMAGE_TAG}${NC}"
echo "Password: ${PASSWORD:0:3}*** (hidden)"
echo ""

# Check if we're in the right directory
if [ ! -f "Dockerfile" ]; then
    echo -e "${RED}❌ Dockerfile not found. Please run this script from the AxonOS root directory.${NC}"
    exit 1
fi

# Validate paths
echo "Validating Dockerfile paths..."
if [ ! -d "axonos_assistant" ]; then
    echo -e "${RED}❌ axonos_assistant directory not found${NC}"
    exit 1
fi

if [ ! -f "novnc-theme/axonos-theme.css" ]; then
    echo -e "${RED}❌ novnc-theme/axonos-theme.css not found${NC}"
    exit 1
fi

echo -e "${GREEN}✓ All paths validated${NC}"
echo ""

# Build the image
echo -e "${GREEN}Starting Docker build...${NC}"
echo "This may take 15-30 minutes depending on your system and network speed."
echo ""

START_TIME=$(date +%s)

if docker build --build-arg PASSWORD="$PASSWORD" -t "$IMAGE_TAG" .; then
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    MINUTES=$((DURATION / 60))
    SECONDS=$((DURATION % 60))
    
    echo ""
    echo -e "${GREEN}✅ Build completed successfully!${NC}"
    echo "Build time: ${MINUTES}m ${SECONDS}s"
    echo ""
    echo "Image created: ${IMAGE_TAG}"
    echo ""
    echo "To run the container (secure-by-default: publish noVNC only):"
    echo "  docker run -d --gpus all --env-file .env -p 6080:6080 \\"
    echo "    --name axonos ${IMAGE_TAG}"
    echo ""
    echo "Advanced (publish VNC + IPFS ports if you explicitly need host access):"
    echo "  docker run -d --gpus all --env-file .env -p 6080:6080 \\"
    echo "    -p 5901:5901 \\"
    echo "    -p 4001:4001 -p 4001:4001/udp -p 5001:5001 -p 8080:8080 -p 9090:9090 \\"
    echo "    --name axonos ${IMAGE_TAG}"
    echo ""
    echo "Then access at: http://localhost:6080/vnc.html"
    echo ""
    
    # Show image info
    echo "Image details:"
    docker images "$IMAGE_TAG" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
    
    exit 0
else
    echo ""
    echo -e "${RED}❌ Build failed!${NC}"
    echo "Check the error messages above for details."
    exit 1
fi
