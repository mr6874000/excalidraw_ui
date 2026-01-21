#!/usr/bin/env python3
"""
generate_compose.py

Usage:
  python generate_compose.py --app relationshiphub --host-port 11015
  python generate_compose.py

This writes docker-compose.yaml in the current directory.
If arguments are not provided, it prompts the user for them.
"""

import argparse
import sys
from pathlib import Path

REGISTRY = "docker.1tushar.com"
CONTAINER_PORT = 5000
HOST_DATA_ROOT = "/mnt/v1c20r_1/Softwares/docker"  # /data -> {HOST_DATA_ROOT}/{app}
OUTPUT_FILE = "docker-compose.yaml"
TIMEZONE = "America/New_York"  # NY EST/EDT

TEMPLATE = """version: "3.9"

services:
  {app}:
    image: {registry}/{app}
    container_name: {app}
    restart: unless-stopped
    pull_policy: always
    ports:
      - "{host_port}:{container_port}"
    volumes:
      - {host_data_root}/{app}:/app/data
    environment:
      - TZ={timezone}
"""

def valid_port(value: str) -> int:
    """Checks if a string is a valid port number."""
    try:
        port = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("Port must be an integer.")
    if not (1 <= port <= 65535):
        raise argparse.ArgumentTypeError("Port must be between 1 and 65535.")
    return port

def main():
    """Parses args or prompts user to generate the docker-compose file."""
    parser = argparse.ArgumentParser(
        description="Generate docker-compose.yaml, prompting for info if not supplied."
    )
    parser.add_argument("--app", help="App name (e.g., relationshiphub)")
    parser.add_argument("--host-port", type=valid_port, help=f"Host port to map to container {CONTAINER_PORT}")
    parser.add_argument("--out", default=OUTPUT_FILE, help=f"Output file (default: {OUTPUT_FILE})")
    args = parser.parse_args()

    app_name = args.app
    host_port = args.host_port

    # Prompt for app name if it wasn't passed as an argument
    if not app_name:
        while True:
            app_name = input("Enter the app name: ").strip()
            if app_name:
                break
            print("Error: App name cannot be empty.")

    # Prompt for host port if it wasn't passed as an argument
    if not host_port:
        while True:
            port_str = input(f"Enter the host port to map to container port {CONTAINER_PORT}: ").strip()
            try:
                # Reuse the validation function
                host_port = valid_port(port_str)
                break
            except argparse.ArgumentTypeError as e:
                print(f"Invalid port. {e}")

    content = TEMPLATE.format(
        app=app_name,
        registry=REGISTRY,
        host_port=host_port,
        container_port=CONTAINER_PORT,
        host_data_root=HOST_DATA_ROOT,
        timezone=TIMEZONE, # Pass the timezone to the template
    )

    out_path = Path(args.out)
    out_path.write_text(content, encoding="utf-8")
    print(f"✅ Wrote docker-compose file to: {out_path.resolve()}")

if __name__ == "__main__":
    sys.exit(main())