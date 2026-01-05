#!/usr/bin/env python3
"""
AxonOS Launcher CLI - Command-line interface for customizing and deploying AxonOS
Designed for headless GPU servers without GUI support
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
import yaml

# Import core launcher logic (without GUI dependencies)
sys.path.insert(0, str(Path(__file__).parent))
from launcher_core import AxonOSLauncherCore

def list_applications(core):
    """List all available applications"""
    print("\n📦 Available Applications:\n")
    all_apps = core.get_all_applications()
    
    for app_id, app_info in sorted(all_apps.items()):
        status = "✓" if app_info.get('enabled', False) else " "
        custom = "🧩" if app_id.startswith('custom_') else "  "
        print(f"  {status} {custom} {app_info['name']}")
        print(f"      {app_info['description']}")
        print()

def generate_dockerfile(core, config_file=None, output='Dockerfile.custom'):
    """Generate custom Dockerfile from configuration"""
    if config_file:
        with open(config_file, 'r') as f:
            config = json.load(f)
        core.load_config(config)
    
    try:
        core.generate_dockerfile(output)
        print(f"✅ Generated custom Dockerfile: {output}")
        return True
    except Exception as e:
        print(f"❌ Error generating Dockerfile: {e}")
        return False

def build_image(core, image_tag='axonos:latest', dockerfile=None):
    """Build Docker image"""
    print(f"🔨 Building Docker image: {image_tag}")
    
    if dockerfile:
        dockerfile_path = dockerfile
    elif core.is_default_configuration():
        dockerfile_path = 'Dockerfile'
        print("✨ Using default configuration - building from original Dockerfile")
    else:
        if not os.path.exists('Dockerfile.custom'):
            print("❌ Dockerfile.custom not found. Generate it first with 'generate' command")
            return False
        dockerfile_path = 'Dockerfile.custom'
        print("🔧 Using custom configuration - building from Dockerfile.custom")
    
    cmd = ['docker', 'build', '-f', dockerfile_path, '-t', image_tag, '.']
    print(f"Running: {' '.join(cmd)}")
    
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                              universal_newlines=True, bufsize=1)
    
    for line in process.stdout:
        print(line.rstrip())
    
    process.wait()
    
    if process.returncode == 0:
        print(f"\n✅ Successfully built image: {image_tag}")
        return True
    else:
        print(f"\n❌ Build failed with return code: {process.returncode}")
        return False

def deploy_image(image_tag='axonos:latest', container_name='axonos', gpu=False, ports_only=False):
    """Deploy Docker container"""
    # Check if image exists
    result = subprocess.run(['docker', 'images', '-q', image_tag], 
                          capture_output=True, text=True)
    if not result.stdout.strip():
        print(f"❌ Docker image '{image_tag}' not found. Please build the image first.")
        return False
    
    # Stop and remove existing container
    subprocess.run(['docker', 'stop', container_name], capture_output=True)
    subprocess.run(['docker', 'rm', container_name], capture_output=True)
    
    # Build docker run command
    docker_cmd = ['docker', 'run', '-d']
    
    if gpu:
        docker_cmd.extend(['--gpus', 'all'])
    
    # Port mappings
    docker_cmd.extend([
        '-p', '6080:6080',  # noVNC
        '-p', '5901:5901',  # VNC
    ])
    
    if not ports_only:
        docker_cmd.extend([
            '-p', '4001:4001',      # IPFS swarm TCP
            '-p', '4001:4001/udp',  # IPFS swarm UDP
            '-p', '5001:5001',      # IPFS API
            '-p', '8080:8080',      # IPFS Gateway
            '-p', '9090:9090',      # IPFS Web UI
        ])
    
    docker_cmd.extend(['--name', container_name, image_tag])
    
    print(f"🚀 Deploying container: {container_name}")
    print(f"Running: {' '.join(docker_cmd)}")
    
    result = subprocess.run(docker_cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        container_id = result.stdout.strip()[:12]
        print(f"✅ Container started successfully: {container_id}")
        print(f"\n🌐 Access AxonOS at: http://localhost:6080/vnc.html")
        if not ports_only:
            print(f"📡 IPFS Gateway: http://localhost:8080")
            print(f"🔧 IPFS API: http://localhost:5001")
            print(f"📁 IPFS Web UI: http://localhost:5001/webui")
        print(f"\n💡 To stop: docker stop {container_name}")
        return True
    else:
        print(f"❌ Failed to start container: {result.stderr}")
        return False

def save_config(core, filename='axonos-config.json'):
    """Save current configuration to file"""
    config = core.get_config()
    with open(filename, 'w') as f:
        json.dump(config, f, indent=2)
    print(f"✅ Configuration saved to: {filename}")

def load_config(core, filename):
    """Load configuration from file"""
    with open(filename, 'r') as f:
        config = json.load(f)
    core.load_config(config)
    print(f"✅ Configuration loaded from: {filename}")

def main():
    parser = argparse.ArgumentParser(
        description="AxonOS Launcher CLI - Build and deploy AxonOS on headless GPU servers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List available applications
  axonos list

  # Generate Dockerfile with default settings
  axonos generate

  # Build image
  axonos build

  # Build and deploy with GPU support
  axonos build --gpu && axonos deploy --gpu

  # Use config file
  axonos generate --config my-config.json
  axonos build --config my-config.json

  # Deploy with custom settings
  axonos deploy --image axonos:custom --name my-axonos --gpu
        """
    )
    
    parser.add_argument('--version', '-v', action='version', version='AxonOS Launcher CLI 0.1.0')
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List available applications')
    
    # Generate command
    generate_parser = subparsers.add_parser('generate', help='Generate custom Dockerfile')
    generate_parser.add_argument('--config', '-c', help='Configuration file (JSON)')
    generate_parser.add_argument('--output', '-o', default='Dockerfile.custom', 
                                help='Output Dockerfile path')
    
    # Build command
    build_parser = subparsers.add_parser('build', help='Build Docker image')
    build_parser.add_argument('--image', '-i', default='axonos:latest', 
                             help='Docker image tag')
    build_parser.add_argument('--dockerfile', '-f', help='Dockerfile path')
    build_parser.add_argument('--config', '-c', help='Configuration file (JSON)')
    build_parser.add_argument('--password', '-p', help='VNC password for build')
    
    # Deploy command
    deploy_parser = subparsers.add_parser('deploy', help='Deploy Docker container')
    deploy_parser.add_argument('--image', '-i', default='axonos:latest', 
                              help='Docker image tag')
    deploy_parser.add_argument('--name', '-n', default='axonos', 
                              help='Container name')
    deploy_parser.add_argument('--gpu', action='store_true', 
                              help='Enable GPU support')
    deploy_parser.add_argument('--ports-only', action='store_true',
                              help='Only expose VNC ports (no IPFS ports)')
    
    # Config command
    config_parser = subparsers.add_parser('config', help='Configuration management')
    config_subparsers = config_parser.add_subparsers(dest='config_action')
    
    save_config_parser = config_subparsers.add_parser('save', help='Save current config')
    save_config_parser.add_argument('--file', '-f', default='axonos-config.json',
                                   help='Config file path')
    
    load_config_parser = config_subparsers.add_parser('load', help='Load config file')
    load_config_parser.add_argument('--file', '-f', required=True, help='Config file path')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Check if we're in the right directory
    if not os.path.exists('Dockerfile'):
        print("❌ Dockerfile not found. Please run from AxonOS root directory.")
        return 1
    
    # Initialize core launcher
    try:
        core = AxonOSLauncherCore()
    except Exception as e:
        print(f"❌ Error initializing launcher: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Execute command
    if args.command == 'list':
        list_applications(core)
        return 0
    
    elif args.command == 'generate':
        success = generate_dockerfile(core, args.config, args.output)
        return 0 if success else 1
    
    elif args.command == 'build':
        if args.config:
            load_config(core, args.config)
        if args.password:
            core.set_password(args.password)
        success = build_image(core, args.image, args.dockerfile)
        return 0 if success else 1
    
    elif args.command == 'deploy':
        success = deploy_image(args.image, args.name, args.gpu, args.ports_only)
        return 0 if success else 1
    
    elif args.command == 'config':
        if args.config_action == 'save':
            save_config(core, args.file)
            return 0
        elif args.config_action == 'load':
            load_config(core, args.file)
            return 0
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
