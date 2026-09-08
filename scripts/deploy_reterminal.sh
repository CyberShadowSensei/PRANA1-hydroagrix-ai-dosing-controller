#!/usr/bin/env bash
# Automated Deployment Script for Seeed reTerminal SBC
set -euo pipefail

echo "==> Deploying Prana 1 to Seeed reTerminal..."
git pull origin main
sudo systemctl restart prana-backend.service
sudo systemctl restart nginx.service
echo "==> Deployment Complete! System active."
