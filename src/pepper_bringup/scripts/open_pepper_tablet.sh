#!/bin/bash

PEPPER_IP="192.168.100.20"

echo "Opening Pepper dashboard on tablet..."
echo "Pepper IP: ${PEPPER_IP}"

ssh nao@${PEPPER_IP} "python2 ~/open_dashboard.py"