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

class EnvController:
    def __init__(self, name = "robot", logger = None):
        self.logger = logger
        self.name = name

        self.memory = 100 * [0]

        # self.env_rpc_server = RpcServer(topic = name + ":env", func = self.env_callback)
        self.env_rpc_server = RPCServer(conn_params=AmqpParams.get(), on_request=self.env_callback, rpc_name=name + ":env")

    def start(self):
        self.env_rpc_server.run()
        self.logger.info("Robot {}: env_rpc_server started".format(self.name))

    def memory_write(self, data):
        del self.memory[-1]
        self.memory.insert(0, data)
        self.logger.info("Robot {}: memory updated for {}".format(self.name, "leds"))

    def env_callback(self, message, meta):
        self.logger.info("Robot {}: Env callback: {}".format(self.name, message))
        try:
            _to = message["from"] + 1
            _from = message["to"]
        except Exception as e:
            self.logger.error("{}: Malformed message for env: {} - {}".format(self.name, str(e.__class__), str(e)))
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
                "temperature": float(random.uniform(30, 10)),
                "pressure": float(random.uniform(30, 10)),
                "humidity": float(random.uniform(30, 10)),
                "gas": float(random.uniform(30, 10))
            })
        return ret
