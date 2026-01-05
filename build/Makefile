# AxonOS Launcher Build System
# =============================

.PHONY: all binary package deb dmg exe cross clean install uninstall help

# Default target
all: binary package

# Build binary only
binary:
	@echo "🔨 Building AxonOS Launcher binary..."
	python3 build_launcher.py

# Build binary and package
package: binary
	@echo "📦 Building AxonOS Launcher package..."
	python3 build_deb.py

# Complete build (binary + package + release info)
release:
	@echo "🚀 Building complete AxonOS Launcher release..."
	python3 build_all.py

# Build .deb package only (requires existing binary)
deb:
	@echo "📦 Building .deb package..."
	python3 build_deb.py

# Build macOS DMG (requires macOS)
dmg:
	@echo "🍎 Building macOS DMG..."
	python3 build_macos.py

# Build Windows EXE (requires Windows)
exe:
	@echo "🪟 Building Windows EXE..."
	python3 build_windows.py

# Build cross-platform packages from Linux
cross:
	@echo "🌍 Building cross-platform packages from Linux..."
	python3 build_simple_cross.py

# Install the binary system-wide (Linux/macOS)
install:
	@echo "📥 Installing AxonOS Launcher..."
	@if [ -f "axonos-launcher_*.deb" ]; then \
		echo "Installing via .deb package..."; \
		sudo dpkg -i axonos-launcher_*.deb; \
		sudo apt-get install -f; \
	elif [ -f "dist/axonos" ]; then \
		echo "Installing binary manually..."; \
		sudo cp dist/axonos /usr/local/bin/; \
		sudo chmod +x /usr/local/bin/axonos; \
		echo "✓ AxonOS Launcher installed to /usr/local/bin/axonos"; \
	elif [ -d "dist/axonos.app" ]; then \
		echo "Installing macOS app..."; \
		cp -r dist/axonos.app /Applications/; \
		echo "✓ AxonOS Launcher installed to /Applications/axonos.app"; \
	else \
		echo "❌ No binary or package found. Run 'make binary' first."; \
		exit 1; \
	fi

# Uninstall the launcher
uninstall:
	@echo "📤 Uninstalling AxonOS Launcher..."
	@if dpkg -l | grep -q axonos-launcher; then \
		echo "Removing via package manager..."; \
		sudo apt remove axonos-launcher; \
	elif [ -f "/usr/local/bin/axonos" ]; then \
		echo "Removing manual installation..."; \
		sudo rm -f /usr/local/bin/axonos; \
		echo "✓ AxonOS Launcher removed from /usr/local/bin/"; \
	elif [ -d "/Applications/axonos.app" ]; then \
		echo "Removing macOS app..."; \
		rm -rf /Applications/axonos.app; \
		echo "✓ AxonOS Launcher removed from /Applications/"; \
	else \
		echo "⚠️  AxonOS Launcher not found in standard locations"; \
	fi

# Clean build artifacts
clean:
	@echo "🧹 Cleaning build artifacts..."
	rm -rf dist/
	rm -rf build/
	rm -f *.spec
	rm -f *.deb
	rm -f RELEASE_INFO.txt
	@echo "✓ Build artifacts cleaned"

# Install build dependencies
deps:
	@echo "📋 Installing build dependencies..."
	pip3 install pyinstaller
	@if [ "$(shell uname)" = "Linux" ]; then \
		echo "Installing Debian packaging tools..."; \
		sudo apt update; \
		sudo apt install -y dpkg-dev gzip; \
	fi
	@echo "✓ Dependencies installed"

# Run the launcher (for testing)
run:
	@echo "🚀 Running AxonOS Launcher..."
	@if [ -f "dist/axonos" ]; then \
		./dist/axonos; \
	elif [ -d "dist/axonos.app" ]; then \
		open dist/axonos.app; \
	elif [ -f "dist/axonos.exe" ]; then \
		./dist/axonos.exe; \
	else \
		echo "No binary found. Running from source..."; \
		python3 axonos_launcher/main.py; \
	fi

# Show help
help:
	@echo "AxonOS Launcher Build System"
	@echo "============================"
	@echo ""
	@echo "Available targets:"
	@echo "  all      - Build binary and package (default)"
	@echo "  binary   - Build binary only"
	@echo "  package  - Build binary and package"
	@echo "  release  - Complete build with release info"
	@echo "  deb      - Build .deb package only"
	@echo "  dmg      - Build macOS DMG package"
	@echo "  exe      - Build Windows EXE package"
	@echo "  cross    - Build all platforms from Linux (Docker required)"
	@echo "  install  - Install launcher system-wide"
	@echo "  uninstall- Remove launcher from system"
	@echo "  clean    - Clean build artifacts"
	@echo "  deps     - Install build dependencies"
	@echo "  run      - Run the launcher (binary or source)"
	@echo "  help     - Show this help message"
	@echo ""
	@echo "Quick start:"
	@echo "  make deps     # Install dependencies"
	@echo "  make release  # Build everything"
	@echo "  make install  # Install system-wide"
	@echo ""
	@echo "Cross-platform build (make cross):"
	@echo "  Linux:   AxonOS-Launcher-0.1.0-Linux-amd64.deb"
	@echo "  macOS:   AxonOS-Launcher-0.1.0-macOS-x86_64.zip (Linux binary)"
	@echo "  Windows: AxonOS-Launcher-0.1.0-Windows-x86_64.zip (Linux binary)"
	@echo ""
	@echo "Native builds (on respective platforms):"
	@echo "  Linux:   AxonOS-Launcher-0.1.0-Linux-amd64.deb"
	@echo "  macOS:   AxonOS-Launcher-0.1.0-macOS-x86_64.dmg (native .app)"
	@echo "  Windows: AxonOS-Launcher-0.1.0-Windows-x86_64.exe (native installer)" 