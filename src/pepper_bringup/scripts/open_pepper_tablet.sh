#!/bin/bash

PEPPER_IP="${PEPPER_IP:-192.168.100.20}"
PEPPER_USER="${PEPPER_USER:-nao}"
HOST_IP="${PEPPER_HOST_IP:-${HOST_IP:-192.168.100.172}}"
DASHBOARD_PORT="${DASHBOARD_PORT:-5000}"

echo "Opening Pepper dashboard on tablet..."
echo "Pepper IP: ${PEPPER_IP}"
echo "Dashboard: http://${HOST_IP}:${DASHBOARD_PORT}/"

ssh "${PEPPER_USER}@${PEPPER_IP}" \
  "PEPPER_HOST_IP='${HOST_IP}' DASHBOARD_PORT='${DASHBOARD_PORT}' python2 ~/open_dashboard.py"
