#!/usr/bin/env bash
# One-time setup of a fresh Ubuntu 24.04 Lightsail server. Run as the default "ubuntu" user:
#   curl -fsSL https://raw.githubusercontent.com/AshokThokala/PayrollEngine-MVP/main/deploy/setup-server.sh | bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/AshokThokala/PayrollEngine-MVP.git}"
APP_DIR="${APP_DIR:-$HOME/clearpay4u}"

echo "==> Updating the system"
sudo apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl git ufw unattended-upgrades fail2ban

echo "==> Installing Docker"
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh
fi
sudo usermod -aG docker "$USER"

echo "==> Adding 2 GB of swap (helps the 2 GB plan build the app)"
if ! sudo swapon --show | grep -q /swapfile; then
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

echo "==> Firewall: SSH, HTTP, HTTPS only"
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 443/udp
sudo ufw --force enable

echo "==> Automatic security updates"
sudo dpkg-reconfigure -f noninteractive unattended-upgrades

echo "==> Getting the code into $APP_DIR"
if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO_URL" "$APP_DIR"
fi
cp -n "$APP_DIR/deploy/.env.example" "$APP_DIR/deploy/.env"
chmod 600 "$APP_DIR/deploy/.env"

echo "==> Nightly database backup at 02:30 server time"
( crontab -l 2>/dev/null | grep -v 'deploy/backup.sh' ; \
  echo "30 2 * * * $APP_DIR/deploy/backup.sh >> $HOME/backup.log 2>&1" ) | crontab -

cat <<MSG

Done. Next:
  1. Log out and back in (so Docker works without sudo).
  2. Fill in the secrets:   nano $APP_DIR/deploy/.env
  3. Point the domain at this server in GoDaddy DNS (see deploy/LIGHTSAIL.md).
  4. Start the app:         $APP_DIR/deploy/deploy.sh
MSG
