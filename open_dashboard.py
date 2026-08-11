# -*- coding: utf-8 -*-
from naoqi import ALProxy
import os
import time

HOST_IP = os.environ.get("PEPPER_HOST_IP", os.environ.get("HOST_IP", "192.168.100.172"))
DASHBOARD_PORT = os.environ.get("DASHBOARD_PORT", "5000")
HOST_DASHBOARD_URL = "http://%s:%s/" % (HOST_IP, DASHBOARD_PORT)

ROBOT_IP = "127.0.0.1"
ROBOT_PORT = 9559

tablet = ALProxy("ALTabletService", ROBOT_IP, ROBOT_PORT)

try:
    tablet.enableWebview(True)
except Exception as e:
    print("enableWebview skipped:", e)

try:
    tablet.hideWebview()
    time.sleep(1)
except Exception:
    pass

try:
    tablet.loadUrl(HOST_DASHBOARD_URL)
    time.sleep(1)
    tablet.showWebview()
    print("Opened dashboard:", HOST_DASHBOARD_URL)
except Exception as e:
    print("Failed to open dashboard:", e)
