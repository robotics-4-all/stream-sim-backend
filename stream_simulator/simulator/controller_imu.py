#!/usr/bin/python
# -*- coding: utf-8 -*-

import time
import json
import math
import logging
import threading
import random

from stream_simulator import Logger

from stream_simulator import AmqpParams
from commlib_py.transports.amqp import RPCServer

class ImuController:
    def __init__(self, name = "robot", logger = None):
        self.logger = logger
        self.name = name

        self.memory = 100 * [0]

        self.imu_rpc_server = RPCServer(conn_params=AmqpParams.get(), on_request=self.imu_callback, rpc_name=name + ":imu")

    def start(self):
        self.imu_rpc_server.run()
        self.logger.info("Robot {}: imu_rpc_server started".format(self.name))

    def memory_write(self, data):
        del self.memory[-1]
        self.memory.insert(0, data)
        self.logger.info("Robot {}: memory updated for {}".format(self.name, "imu"))

    def imu_callback(self, message, meta):
        self.logger.info("Robot {}: Imu callback: {}".format(self.name, message))
        try:
            _to = message["from"] + 1
            _from = message["to"]
        except Exception as e:
            self.logger.error("{}: Malformed message for Imu: {} - {}".format(self.name, str(e.__class__), str(e)))
            return []
        ret = {"data": []}
        for i in range(_from, _to): # 0 to -1
            timestamp = time.time()
            secs = int(timestamp)
            nanosecs = int((timestamp-secs) * 10**(9))
            ret["data"].append({
                "header":{
                    "stamp":{
                        "sec": secs,
                        "nanosec": nanosecs
                    }
                },
                "accel": {
                    "x": 1,
                    "y": 1,
                    "z": 1
                },
                "gyro": {
                    "yaw": random.uniform(0.3, -0.3),
                    "pitch": random.uniform(0.3, -0.3),
                    "roll": random.uniform(0.3, -0.3)
                },
                "magne": {
                    "yaw": random.uniform(0.3, -0.3),
                    "pitch": random.uniform(0.3, -0.3),
                    "roll": random.uniform(0.3, -0.3)
                }
            })
        return ret