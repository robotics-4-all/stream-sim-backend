#!/usr/bin/python
# -*- coding: utf-8 -*-

import time
import json
import math
import logging
import threading
import random

from commlib_py.logger import Logger

from stream_simulator import ConnParams
if ConnParams.type == "amqp":
    from commlib_py.transports.amqp import RPCServer
elif ConnParams.type == "redis":
    from commlib_py.transports.redis import RPCServer

class EncoderController:
    def __init__(self, info = None):
        self.logger = Logger(info["name"] + "-" + info["id"])

        self.info = info
        self.name = info["name"]
        self.conf = info["sensor_configuration"]

        if self.info["mode"] == "real":
            from pidevices import DfRobotWheelEncoderMcp23017
            self.sensor = DfRobotWheelEncoderMcp23017(pin=self.conf["pin"],
                                                      bus=self.conf["bus"],
                                                      address=self.conf["address"],
                                                      name=self.name,
                                                      max_data_length=self.conf["max_data_length"])
            ## https://github.com/robotics-4-all/tektrain-ros-packages/blob/master/ros_packages/robot_hw_interfaces/encoder_hw_interface/encoder_hw_interface/encoder_hw_interface.py

        self.memory = 100 * [0]

        self.encoder_rpc_server = RPCServer(conn_params=ConnParams.get(), on_request=self.encoder_callback, rpc_name=info["base_topic"] + "/get")
        self.enable_rpc_server = RPCServer(conn_params=ConnParams.get(), on_request=self.enable_callback, rpc_name=info["base_topic"] + "/enable")
        self.disable_rpc_server = RPCServer(conn_params=ConnParams.get(), on_request=self.disable_callback, rpc_name=info["base_topic"] + "/disable")

    def sensor_read(self):
        self.logger.info("Encoder {} sensor read thread started".format(self.info["id"]))
        while self.info["enabled"]:
            time.sleep(1.0 / self.info["hz"])

            if self.info["mode"] == "mock":
                self.memory_write(float(random.uniform(1000,2000)))
            elif self.info["mode"] == "simulation":
                self.memory_write(float(random.uniform(1000,2000)))
            else: # The real deal
                self.logger.warning("{} mode not implemented for {}".format(self.info["mode"], self.name))

        self.logger.info("Encoder {} sensor read thread stopped".format(self.info["id"]))

    def enable_callback(self, message, meta):
        self.info["enabled"] = True
        self.info["hz"] = message["hz"]
        self.info["queue_size"] = message["queue_size"]

        self.memory = self.info["queue_size"] * [0]
        self.sensor_read_thread = threading.Thread(target = self.sensor_read)
        self.sensor_read_thread.start()
        return {"enabled": True}

    def disable_callback(self, message, meta):
        self.info["enabled"] = False
        self.logger.info("Encoder {} stops reading".format(self.info["id"]))
        return {"enabled": False}

    def start(self):
        self.encoder_rpc_server.run()
        self.enable_rpc_server.run()
        self.disable_rpc_server.run()

        if self.info["enabled"]:
            self.memory = self.info["queue_size"] * [0]
            self.sensor_read_thread = threading.Thread(target = self.sensor_read)
            self.sensor_read_thread.start()
            self.logger.info("Encoder {} reads with {} Hz".format(self.info["id"], self.info["hz"]))

    def stop(self):
        self.info["enabled"] = False
        self.encoder_rpc_server.stop()
        self.enable_rpc_server.stop()
        self.disable_rpc_server.stop()

    def memory_write(self, data):
        del self.memory[-1]
        self.memory.insert(0, data)
        # self.logger.info("Robot {}: memory updated for {}".format(self.name, "encoder"))

    def encoder_callback(self, message, meta):
        if self.info["enabled"] is False:
            return {"data": []}

        self.logger.info("Robot {}: encoder callback: {}".format(self.name, message))
        try:
            _to = message["from"] + 1
            _from = message["to"]
        except Exception as e:
            self.logger.error("{}: Malformed message for encoder: {} - {}".format(self.name, str(e.__class__), str(e)))
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
                "rpm": self.memory[-i]
            })
        return ret
