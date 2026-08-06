# -*- coding: utf-8 -*-
from naoqi import ALProxy
import time

ROBOT_IP = "127.0.0.1"
PORT = 9559

motion = ALProxy("ALMotion", ROBOT_IP, PORT)
posture = ALProxy("ALRobotPosture", ROBOT_IP, PORT)

print("[posture] waking up Pepper")
motion.wakeUp()

print("[posture] going to StandInit")
posture.goToPosture("StandInit", 0.5)

time.sleep(1.0)

print("[posture] setting head neutral")
motion.setStiffnesses("Head", 1.0)
motion.setAngles(["HeadYaw", "HeadPitch"], [0.0, 0.0], 0.15)

time.sleep(0.5)

print("[posture] correcting hip neutral")
motion.setStiffnesses(["HipPitch", "HipRoll"], 1.0)
motion.setAngles(["HipPitch", "HipRoll"], [0.0, 0.0], 0.12)

time.sleep(0.5)
print("[posture] done")
