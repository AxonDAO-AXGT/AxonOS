#!/bin/bash
# Quick Docker build validation script for AxonOS
# Tests Dockerfile syntax and verifies all paths exist

set -e

echo "🔍 AxonOS Docker Build Validation"
echo "=================================="
echo ""

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed or not in PATH"
    exit 1
fi

echo "✓ Docker is available: $(docker --version)"
echo ""

# Check Dockerfile exists
if [ ! -f "Dockerfile" ]; then
    echo "❌ Dockerfile not found"
    exit 1
fi

echo "✓ Dockerfile found"
echo ""

# Validate all COPY paths exist
echo "Checking COPY paths in Dockerfile..."
errors=0

while IFS= read -r line; do
    if [[ $line =~ ^COPY[[:space:]]+([^[:space:]]+) ]]; then
        src_path="${BASH_REMATCH[1]}"
        # Remove destination part if present
        src_path="${src_path%% *}"
        
        # Skip wildcard patterns and files that might not exist yet
        if [[ "$src_path" == *"*"* ]]; then
            echo "  ⚠️  Wildcard pattern: $src_path (skipping check)"
            continue
        fi
        
        # Check if path exists
        if [ -e "$src_path" ] || [ -d "$src_path" ]; then
            echo "  ✓ $src_path"
        else
            echo "  ❌ $src_path - NOT FOUND"
            errors=$((errors + 1))
        fi
    fi
done < Dockerfile

echo ""

# Check for old branding in Dockerfile
echo "Checking for old branding references..."
if grep -qi "descios" Dockerfile; then
    echo "  ⚠️  Found 'descios' references in Dockerfile:"
    grep -ni "descios" Dockerfile | head -5
    errors=$((errors + 1))
else
    echo "  ✓ No old 'descios' references found"
fi

echo ""

# Check for new branding
echo "Checking for new AxonOS branding..."
if grep -qi "axonos" Dockerfile; then
    echo "  ✓ Found AxonOS branding"
else
    echo "  ⚠️  No AxonOS branding found in Dockerfile"
fi

echo ""

# Summary
if [ $errors -eq 0 ]; then
    echo "✅ Dockerfile validation passed!"
    echo ""
    echo "To build the image, run:"
    echo "  docker build --build-arg PASSWORD=\"$AXONOS_VNC_PASSWORD\" -t axonos:latest ."
    echo ""
    echo "Recommended: Build and run (secure-by-default: publish noVNC only):"
    echo "  docker build --build-arg PASSWORD=\"$AXONOS_VNC_PASSWORD\" -t axonos:latest ."
    echo "  docker run -d --gpus all --env-file .env -p 6080:6080 \\"
    echo "    --name axonos axonos:latest"
    echo ""
    echo "Advanced (publish VNC + IPFS ports if you explicitly need host access):"
    echo "  docker run -d --gpus all --env-file .env -p 6080:6080 \\"
    echo "    -p 5901:5901 \\"
    echo "    -p 4001:4001 -p 4001:4001/udp -p 5001:5001 -p 8080:8080 -p 9090:9090 \\"
    echo "    --name axonos axonos:latest"
    echo ""
    echo "Without GPU (if no NVIDIA GPU available):"
    echo "  docker run -d --env-file .env -p 6080:6080 \\"
    echo "    --name axonos axonos:latest"
    echo ""
    echo "Then access at: http://localhost:6080/vnc.html"
    exit 0
else
    echo "❌ Found $errors issue(s) - please fix before building"
    exit 1
fi
