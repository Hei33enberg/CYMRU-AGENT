#!/bin/bash
# =============================================================================
# CYMRU Agent Provisioning & Deployment Script for Hetzner CX22 VPS
# Operating System: Ubuntu 22.04 LTS / Debian 12 / Debian 13
# =============================================================================

set -e

# Colors for nice output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Starting CYMRU Agent Provisioning on VPS ===${NC}"

# 1. Update system packages
echo -e "${BLUE}[1/5] Updating system packages...${NC}"
sudo apt-get update -y
sudo apt-get upgrade -y
sudo apt-get install -y git curl apt-transport-https ca-certificates gnupg lsb-release

# 2. Install Docker if not present
if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}Docker is not installed. Installing Docker Engine...${NC}"
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    rm get-docker.sh
    echo -e "${GREEN}Docker installed successfully.${NC}"
else
    echo -e "${GREEN}Docker is already installed.${NC}"
fi

# 3. Install Docker Compose plugin if not present
if ! docker compose version &> /dev/null; then
    echo -e "${YELLOW}Docker Compose plugin is not installed. Installing...${NC}"
    sudo apt-get install -y docker-compose-plugin
    echo -e "${GREEN}Docker Compose plugin installed successfully.${NC}"
else
    echo -e "${GREEN}Docker Compose plugin is already installed.${NC}"
fi

# Ensure docker service is enabled and running
sudo systemctl enable docker
sudo systemctl start docker

# 4. Clone CYMRU-AGENT Repository
APP_DIR="/opt/cymru-agent"
echo -e "${BLUE}[3/5] Setting up CYMRU-AGENT codebase in $APP_DIR...${NC}"

if [ ! -d "$APP_DIR" ]; then
    echo -e "${YELLOW}Cloning CYMRU-AGENT repository...${NC}"
    sudo git clone https://github.com/Hei33enberg/CYMRU-AGENT.git "$APP_DIR"
    sudo chown -R $USER:$USER "$APP_DIR"
    echo -e "${GREEN}Cloned repository to $APP_DIR.${NC}"
else
    echo -e "${GREEN}Directory $APP_DIR already exists. Pulling latest changes...${NC}"
    cd "$APP_DIR"
    git pull origin main
fi

cd "$APP_DIR"

# 5. Setup Environment Variables
echo -e "${BLUE}[4/5] Preparing environment files...${NC}"
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}Initializing .env file from template...${NC}"
    cp .env.agent .env
    echo -e "${RED}IMPORTANT: Please edit .env file at $APP_DIR/.env to configure your real credentials before launching!${NC}"
else
    echo -e "${GREEN}.env file already exists. Preservation guaranteed.${NC}"
fi

# Ensure ~/.hermes directory exists for the container volume
mkdir -p ~/.hermes

# 6. Start CYMRU Agent Container
echo -e "${BLUE}[5/5] Building and running docker containers...${NC}"
echo -e "${YELLOW}This may take a few minutes for the initial build...${NC}"

docker compose build
docker compose up -d

echo -e "${GREEN}=== CYMRU Agent Deployment Complete! ===${NC}"
echo -e "${BLUE}Logs can be monitored by running: docker compose logs -f${NC}"
