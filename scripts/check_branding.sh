#!/bin/bash
# Branding check script for AxonOS
# Fails if forbidden old-brand strings are found in the codebase

set -e

FORBIDDEN_PATTERNS=(
    "DeSciOS"
    "descios"
    "DeSci OS"
    "DeSciOS.io"
    "GizmoQuest/DeSciOS"
)

EXEMPT_DIRS=(
    "docs/rebrand"
    ".git"
    "build/__pycache__"
    "build/build_env"
    "build/descios_launcher"
    "build/descios_launcher_linux"
    "__pycache__"
    "node_modules"
    ".pytest_cache"
    "dist"
    "DeSciOS-Launcher-0.1.0-macOS"
    "DeSciOS-Launcher-0.1.0-Windows"
    "data"
)

EXEMPT_FILES=(
    "docs/rebrand/MIGRATION.md"
    "docs/rebrand/INVENTORY.md"
    "scripts/check_branding.sh"
    "scripts/test_docker_build.sh"
)

EXEMPT_EXTENSIONS=(
    ".pyc"
    ".pyo"
    ".sqlite"
    ".db"
    ".toc"
    ".html"
)

ERRORS=0

# Function to check if path is exempt
is_exempt() {
    local path="$1"
    # Normalize paths from grep output (often prefixed with "./")
    path="${path#./}"
    
    # Check exempt directories
    for exempt_dir in "${EXEMPT_DIRS[@]}"; do
        if [[ "$path" == *"$exempt_dir"* ]]; then
            return 0
        fi
    done
    
    # Check exempt files
    for exempt_file in "${EXEMPT_FILES[@]}"; do
        if [[ "$path" == "$exempt_file" ]]; then
            return 0
        fi
    done
    
    # Check exempt extensions
    for ext in "${EXEMPT_EXTENSIONS[@]}"; do
        if [[ "$path" == *"$ext" ]]; then
            return 0
        fi
    done
    
    return 1
}

echo "🔍 Checking for forbidden branding patterns..."

# Search for each forbidden pattern
for pattern in "${FORBIDDEN_PATTERNS[@]}"; do
    echo "  Checking for: $pattern"
    
    # Use grep to find matches, excluding exempt paths
    while IFS= read -r -d '' file; do
        if ! is_exempt "$file"; then
            echo "    ❌ Found in: $file"
            ERRORS=$((ERRORS + 1))
        fi
    done < <(grep -r -l --null "$pattern" . 2>/dev/null || true)
done

if [ $ERRORS -eq 0 ]; then
    echo "✅ No forbidden branding patterns found!"
    exit 0
else
    echo ""
    echo "❌ Found $ERRORS file(s) with forbidden branding patterns"
    echo "   Please update these files to use AxonOS branding"
    echo "   See docs/rebrand/BRAND.md for branding guidelines"
    exit 1
fi
