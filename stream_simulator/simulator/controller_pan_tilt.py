#!/usr/bin/python
# -*- coding: utf-8 -*-

import time
import json
import math
import logging
import threading
import random

from colorama import Fore, Style

from commlib.logger import Logger

from .conn_params import ConnParams
if ConnParams.type == "amqp":
    from commlib.transports.amqp import RPCService, Subscriber
elif ConnParams.type == "redis":
    from commlib.transports.redis import RPCService, Subscriber

class PanTiltController:
    def __init__(self, info = None):
        self.logger = Logger(info["name"] + "-" + info["id"])

        self.info = info
        self.name = info["name"]

        self.memory = 100 * [0]

        self.pan_tilt_set_sub = Subscriber(conn_params=ConnParams.get(), topic =info["base_topic"] + "/set", on_message = self.pan_tilt_set_callback)
        self.logger.info("Created redis Subscriber {}".format(
            info["base_topic"] + "/set"
        ))

        self.pan_tilt_get_server = RPCService(conn_params=ConnParams.get(), on_request=self.pan_tilt_get_callback, rpc_name=info["base_topic"] + "/get")
        self.logger.info("Created redis RPCService {}".format(
            info["base_topic"] + "/get"
        ))

        self.enable_rpc_server = RPCService(conn_params=ConnParams.get(), on_request=self.enable_callback, rpc_name=info["base_topic"] + "/enable")
        self.disable_rpc_server = RPCService(conn_params=ConnParams.get(), on_request=self.disable_callback, rpc_name=info["base_topic"] + "/disable")

    def enable_callback(self, message, meta):
        self.info["enabled"] = True
        return {"enabled": True}

    def disable_callback(self, message, meta):
        self.info["enabled"] = False
        return {"enabled": False}

    def start(self):
        self.pan_tilt_set_sub.run()
        self.pan_tilt_get_server.run()

        self.enable_rpc_server.run()
        self.disable_rpc_server.run()

    def stop(self):
        self.pan_tilt_set_sub.stop()
        self.pan_tilt_get_server.stop()

        self.enable_rpc_server.stop()
        self.disable_rpc_server.stop()

    def memory_write(self, data):
        del self.memory[-1]
        self.memory.insert(0, data)
        self.logger.info("Robot {}: memory updated for {}".format(self.name, "pan_tilt"))

    def pan_tilt_get_callback(self, message, meta):
        self.logger.info("Robot {}: Pan tilt get callback: {}".format(self.name, message))
        try:
            _to = message["from"] + 1
            _from = message["to"]
        except Exception as e:
            self.logger.error("{}: Malformed message for pan tilt get: {} - {}".format(self.name, str(e.__class__), str(e)))
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
                "yaw": self.memory[-i][0],
                "pitch": self.memory[-i][1],
                "deviceId": 0
            })
        return ret

    def pan_tilt_set_callback(self, message, meta):
        try:

            response = message
            self._yaw = response['yaw']
            self._pitch = response['pitch']
            self.memory_write([self._yaw, self._pitch])

            if self.info["mode"] == "mock":
                pass
            elif self.info["mode"] == "simulation":
                pass
            else: # The real deal
                self.logger.warning("{} mode not implemented for {}".format(self.info["mode"], self.name))


            self.logger.info("{}: New pan tilt command: {}, {}".format(self.name, self._yaw, self._pitch))
        except Exception as e:
            self.logger.error("{}: pan_tilt is wrongly formatted: {} - {}".format(self.name, str(e.__class__), str(e)))
