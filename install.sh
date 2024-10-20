#!/bin/bash

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

printHeader() {
    echo -e "${CYAN}   ___       *      *                       ${NC}"
    echo -e "${CYAN}  / * \\     | |    (*)                      ${NC}"
    echo -e "${CYAN} | | | |_  *| |     * *_* ___   ___  *_*  ${NC}"
    echo -e "${CYAN} | | | \\ \\/ / |    | | '_ ' * \\ / * \\| '_ \\ ${NC}"
    echo -e "${CYAN} | |_| |>  <| |____| | | | | | | (_) | | | |${NC}"
    echo -e "${CYAN}  \\___//_/\\_\\______|_|_| |_| |_|\\___/|_| |_|${NC}"
    echo -e "${CYAN}                                            ${NC}"
    echo -e "${CYAN}                                            ${NC}"
    echo -e "${CYAN}  https://github.com/0xlimon${NC}"
    echo -e "${CYAN}******************************************************${NC}"
}

installBot() {
    # Check if script is run as root
    if [[ $EUID -ne 0 ]]; then
       echo -e "${RED}This script must be run as root${NC}" 
       exit 1
    fi

    # Update and install dependencies
    echo -e "${YELLOW}Updating system and installing dependencies...${NC}"
    apt update && apt upgrade -y
    apt install -y python3 python3-pip git

    # Install Python packages
    echo -e "${YELLOW}Installing required Python packages...${NC}"
    pip3 install aiohttp==3.10.8 psutil==6.0.0 python-dotenv==1.0.1 python-telegram-bot==21.6

    # Create directory for the bot
    BOT_DIR="/root/story-telegram-bot"
    echo -e "${YELLOW}Creating directory for the bot at ${BOT_DIR}...${NC}"
    mkdir -p $BOT_DIR
    cd $BOT_DIR

    # Download the bot script
    echo -e "${YELLOW}Downloading the bot script...${NC}"
    wget -O bot.py https://raw.githubusercontent.com/0xlimon/story-wave2-task4-Useful-utility-for-validators/main/bot.py

    # Create .env file
    echo -e "${GREEN}Creating .env file...${NC}"
    echo -e "${BLUE}Please provide the following information:${NC}"

    read -p "Enter your Telegram Bot Token: " bot_token
    read -p "Enter the monitoring interval in minutes: " monitoring_interval
    read -p "Enter the node port (default 26657): " server_port
    server_port=${server_port:-26657}
    read -p "Enter your Telegram Admin ID: " admin_id

    read -p "Enter the name of the Story service (default 'story'): " story_service
    story_service=${story_service:-story}
    read -p "Enter the name of the Story Geth service (default 'story-geth'): " story_geth_service
    story_geth_service=${story_geth_service:-story-geth}

    # Convert monitoring interval to seconds
    monitoring_interval_seconds=$((monitoring_interval * 60))

    cat > $BOT_DIR/.env << EOL
BOT_TOKEN=${bot_token}
MONITORING_INTERVAL=${monitoring_interval_seconds}
SERVER_PORT=${server_port}
ADMIN_ID=${admin_id}
RPC_ENDPOINT_1=https://archive-rpc-story.josephtran.xyz/status
RPC_ENDPOINT_2=https://story-testnet-rpc.itrocket.net/status
STORY_SERVICE=${story_service}
STORY_GETH_SERVICE=${story_geth_service}
EOL

    echo -e "${GREEN}.env file created successfully in ${BOT_DIR}!${NC}"

    # Create systemd service file
    echo -e "${YELLOW}Creating systemd service file...${NC}"
    cat > /etc/systemd/system/story-telegram-bot.service << EOL
[Unit]
Description=Story Telegram Bot Service
After=network.target

[Service]
ExecStart=/usr/bin/python3 ${BOT_DIR}/bot.py
WorkingDirectory=${BOT_DIR}
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOL

    # Reload systemd, enable and start the service
    systemctl daemon-reload
    systemctl enable story-telegram-bot
    systemctl start story-telegram-bot

    echo -e "${GREEN}Story Telegram Bot has been installed and started as a service!${NC}"
    echo -e "${MAGENTA}Here are some useful commands:${NC}"
    echo -e "${CYAN}View logs: ${NC}journalctl -u story-telegram-bot -f"
    echo -e "${CYAN}Restart bot: ${NC}systemctl restart story-telegram-bot"
    echo -e "${CYAN}Stop bot: ${NC}systemctl stop story-telegram-bot"
    echo -e "${CYAN}Start bot: ${NC}systemctl start story-telegram-bot"
    echo -e "${CYAN}Check status: ${NC}systemctl status story-telegram-bot"

    echo -e "${GREEN}Installation complete! Your Story Telegram Bot should now be running.${NC}"
    echo -e "${YELLOW}Bot installation directory: ${BOT_DIR}${NC}"
}

uninstallBot() {
    echo -e "${YELLOW}Uninstalling Story Telegram Bot...${NC}"

    # Stop and disable the service
    systemctl stop story-telegram-bot
    systemctl disable story-telegram-bot

    # Remove the service file
    rm /etc/systemd/system/story-telegram-bot.service

    # Remove the bot directory
    rm -rf /opt/story-telegram-bot

    # Reload systemd
    systemctl daemon-reload

    echo -e "${GREEN}Story Telegram Bot has been uninstalled successfully!${NC}"
}

# Main menu
while true; do
    printHeader
    echo -e "${BLUE}Please select an option:${NC}"
    echo "1) Install Story Telegram Bot"
    echo "2) Uninstall Story Telegram Bot"
    echo "3) Exit"
    read -p "Enter your choice (1-3): " choice

    case $choice in
        1)
            installBot
            ;;
        2)
            uninstallBot
            ;;
        3)
            echo -e "${GREEN}Exiting. Goodbye!${NC}"
            exit 0
            ;;
        *)
            echo -e "${RED}Invalid option. Please try again.${NC}"
            ;;
    esac

    echo
    read -p "Press Enter to return to the main menu..."
done
