#!/usr/bin/env python3
"""
Quick validation test for Auto-Vote-Rating Docker setup.
Run this before starting the container to ensure Python environment is correct.
"""

import sys
import subprocess

def check_python_version():
    """Check Python version"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("❌ Python 3.8+ required")
        return False
    print(f"✅ Python {version.major}.{version.minor}.{version.micro}")
    return True

def check_module(module_name):
    """Check if a Python module is importable"""
    try:
        __import__(module_name)
        print(f"✅ {module_name}")
        return True
    except ImportError:
        print(f"❌ {module_name} not found")
        return False

def check_docker():
    """Check if Docker is installed"""
    try:
        result = subprocess.run(['docker', '--version'], 
                              capture_output=True, 
                              text=True, 
                              timeout=5)
        if result.returncode == 0:
            print(f"✅ Docker: {result.stdout.strip()}")
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    print("❌ Docker not found")
    return False

def check_docker_compose():
    """Check if Docker Compose is installed"""
    try:
        result = subprocess.run(['docker-compose', '--version'], 
                              capture_output=True, 
                              text=True, 
                              timeout=5)
        if result.returncode == 0:
            print(f"✅ Docker Compose: {result.stdout.strip()}")
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    print("❌ Docker Compose not found")
    return False

def main():
    print("=" * 50)
    print("Auto-Vote-Rating Docker Validation")
    print("=" * 50)
    print()
    
    results = []
    
    print("Checking Python environment...")
    results.append(check_python_version())
    print()
    
    print("Checking required Python modules...")
    modules = ['flask', 'playwright', 'schedule', 'requests', 'bs4', 'apscheduler', 'yaml']
    for module in modules:
        results.append(check_module(module))
    print()
    
    print("Checking Docker...")
    results.append(check_docker())
    results.append(check_docker_compose())
    print()
    
    print("=" * 50)
    if all(results):
        print("✅ All checks passed! Ready to run.")
        print()
        print("To start the container:")
        print("  docker-compose up -d")
        print()
        print("To view logs:")
        print("  docker-compose logs -f")
        return 0
    else:
        print("❌ Some checks failed. Please install missing dependencies.")
        print()
        print("To install Python dependencies:")
        print("  pip install -r requirements.txt")
        print("  playwright install chromium")
        print()
        print("Note: Python dependencies are only needed for local testing.")
        print("Docker will install them automatically in the container.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
