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
from stream_simulator.connectivity import CommlibFactory
from stream_simulator.base_classes import BaseThing

class MotionController(BaseThing):
    def __init__(self, conf = None, package = None):
        if package["logger"] is None:
            self.logger = Logger(conf["name"])
        else:
            self.logger = package["logger"]

        super(self.__class__, self).__init__()
        id = "d_" + str(BaseThing.id)
        name = id
        if 'name' in conf:
            name = conf['name']
        _category = "actuator"
        _class = "motion"
        _subclass = "twist"
        _pack = package["name"]

        info = {
            "type": "SKID_STEER",
            "brand": "twist",
            "base_topic": f"{_pack}.{_category}.{_class}.{_subclass}.{name}",
            "name": name,
            "place": conf["place"],
            "id": id,
            "enabled": True,
            "orientation": conf["orientation"],
            "queue_size": 0,
            "mode": package["mode"],
            "namespace": package["namespace"],
            "sensor_configuration": conf["sensor_configuration"],
            "device_name": package["device_name"],
            "categorization": {
                "host_type": "robot",
                "place": _pack.split(".")[-1],
                "category": _category,
                "class": _class,
                "subclass": [_subclass],
                "name": name
            }
        }

        self.info = info
        self.name = info["name"]
        self.conf = info["sensor_configuration"]
        self.base_topic = info["base_topic"]
        self.derp_data_key = info["base_topic"] + ".raw"

        # tf handling
        tf_package = {
            "type": "robot",
            "subtype": {
                "category": _category,
                "class": _class,
                "subclass": [_subclass]
            },
            "pose": conf["pose"],
            "base_topic": info['base_topic'],
            "name": self.name
        }
        tf_package['host'] = package['device_name']
        tf_package['host_type'] = 'robot'
        package["tf_declare"].call(tf_package)

        self._motor_driver = None

        if self.info["mode"] == "real":
            from pidevices import DfrobotMotorControllerPiGPIO

            self._motor_driver = DfrobotMotorControllerPiGPIO(E1=self.conf["E1"], 
                                                             M1=self.conf["M1"], 
                                                             E2=self.conf["E2"], 
                                                             M2=self.conf["M2"])

            self._init_delay = 7
        else: 
            self._init_delay = 1
            
            
        self.wheel_separation = self.conf["wheel_separation"]
        self.wheel_radius = self.conf["wheel_radius"]

        self._linear = 0
        self._angular = 0

        self.device_finder = CommlibFactory.getRPCClient(
            broker="redis",            
            rpc_name = f"robot.{self.info['device_name']}.nodes_detector.get_connected_devices"
        )

        # motion controller depends on other controller (imu, line follower, encoders)
        # in order to work. So it needs to wait to the other controllers are initialized so 
        # it can identify at runtime throw their topic
        
        # give some time so all other the controllers are initialized
        
        self.initializer = threading.Thread(target=self._init, args=(self._init_delay,), daemon=True)

        # publisher that exports robots velocities to other modules across streamsim
        self.velocities_publisher = CommlibFactory.getPublisher(
            broker = "redis",
            topic = info["base_topic"] + ".data"
        )
        
        # action service that moves robot (linearly/rotationally)
        self.move_action_server = CommlibFactory.getActionServer(
            broker = "redis",
            callback = self.on_goal_cmd_vel,
            action_name = info["base_topic"] + ".set"
        )

        # rpc service that calibrates motion
        self.motion_calibration_server = CommlibFactory.getRPCService(
            broker = "redis",
            callback = self.calibrate_motion,
            rpc_name = info["base_topic"] + ".calibrate"
        )
        
        # action service that starts line following
        self.lf_action_server = CommlibFactory.getActionServer(
            broker = "redis",
            callback = self.on_goal_follow_line,
            action_name = info["base_topic"] + ".follow_line"
        )

        # rpc service which starts the motion controller
        self.enable_rpc_server = CommlibFactory.getRPCService(
            broker = "redis",
            callback = self.enable_callback,
            rpc_name = info["base_topic"] + ".enable"
        )
        
        # rpc service which terminates the motion controller
        self.disable_rpc_server = CommlibFactory.getRPCService(
            broker = "redis",
            callback = self.disable_callback,
            rpc_name = info["base_topic"] + ".disable"
        )

    # records topics and names of IMU, LF and ENCODER robot devices
    def record_devices(self, available_devices):
        self._imu_topic = None
        self._enc_left_topic = None
        self._enc_left_name = None
        self._enc_right_topic = None
        self._enc_right_name = None
        self._lf_topic = None
        self._servo_topic = None

        #print(available_devices["devices"])
        for d in available_devices['devices']:
            if d['type'] == "IMU":
                self._imu_topic = d['base_topic'] + ".data"
            elif d['type'] == "ENCODER":
                if d['place'] == "BL":
                    self._enc_left_topic = d['base_topic'] + ".data"
                    self._enc_left_name = d["sensor_configuration"]["name"]
                    self._enc_freq = d["hz"]
                elif d['place'] == "BR":
                    self._enc_right_topic = d['base_topic'] + ".data"
                    self._enc_right_name = d["sensor_configuration"]["name"]
            elif d['type'] == "LINE_FOLLOWER":
                self._lf_topic = d['base_topic'] + ".data"
            elif d['type'] == "SERVO":
                self._servo_topic = d['base_topic'] + ".set"

    def calibrate_motion(self):
        pass
    
    def _enc_left_callback(self, message, meta):
        #self.logger.info("Left encoder callback: {}".format(message))
        self._speed_controller.update({
            'rps': message['rps'],
            'enc': self._enc_left_name
        })

    def _enc_right_callback(self, message, meta):
        #self.logger.info("Right encoder callback: {}".format(message))
        self._speed_controller.update({
            'rps': message['rps'],
            'enc': self._enc_right_name
        })

    def _imu_callback(self, message, meta):
        #self.logger.info("Imu message: {}".format(message))
        self._dirr_controller.update(message['data'])   

    def _lf_callback(self, message, meta):
        #self.logger.info("Line follower callback: {}".format(message))
        self._lf_controller.update(list(message.values()))  

    # publish velocities across streamsim in order to be used from robot/simulator
    def _publish_velocities_cb(self, linear, rotational):
        self.velocities_publisher.publish({
            'linear': linear,
            'rotational': rotational 
        })

    def _init(self, delay):
        # wait for all controller to be initialized
        time.sleep(delay)
        self.logger.info("=============== Motion controller initialized ===================")
        
        if self.info["mode"] == "mock":
            pass
        elif self.info["mode"] == "simulation":
            from robot_motion.complex_motion import ComplexMotionSimulator

            self._complex_controller = ComplexMotionSimulator(callback=self._publish_velocities_cb)
        else: # The real deal
            # record available sensor devices after all controller have been initialized
            available_devices = self.device_finder.call({})
            #print("available devices" ,available_devices)
            self.record_devices(available_devices=available_devices)

            from robot_motion import SpeedController, DirectionController, LineFollower, ComplexMotion

            # intialize speed controller of the robot
            path = "../stream_simulator/settings/pwm_to_wheel_rps.json"
            self._speed_controller = SpeedController(wheel_radius=self.wheel_radius,
                                                    enc_left_name=self._enc_left_name,
                                                    enc_right_name=self._enc_right_name,
                                                    path_to_settings=path)

            # initialize the direction controller of the robot
            path = "../stream_simulator/settings/heading_converter.json"
            self._dirr_controller = DirectionController(path_to_heading_settings=path)

            # initialize the line follower controller 
            self._lf_controller = LineFollower(speed=0.35, logger=self.logger)

            # initialize the complex motion controller which is an interface for communicate with both the previous two
            self._complex_controller = ComplexMotion(motor_driver=self._motor_driver, 
                                                    speed_controller=self._speed_controller, 
                                                    direction_controller=self._dirr_controller, 
                                                    line_follower=self._lf_controller,
                                                    callback=self._publish_velocities_cb)

            # subscribe to imu's topic
            if self._imu_topic is not None:
                self._imu_sub = CommlibFactory.getSubscriber(
                    broker = "redis",
                    topic = self._imu_topic,
                    callback = self._imu_callback
                )
                self._imu_sub.run()

            # subscribe to left encoder's topic
            if self._enc_left_topic is not None:
                self._enc_left_sub = CommlibFactory.getSubscriber(
                    broker = "redis",
                    topic = self._enc_left_topic,
                    callback = self._enc_left_callback
                )
                self._enc_left_sub.run()

            # subscribe to right encoder's topic
            if self._enc_right_topic is not None:
                self._enc_right_sub = CommlibFactory.getSubscriber(
                    broker = "redis",
                    topic = self._enc_right_topic,
                    callback = self._enc_right_callback
                )
                self._enc_right_sub.run()

            #subscribe to line follower's topic
            if self._lf_topic is not None:
                self._lf_sub = CommlibFactory.getSubscriber(
                    broker = "redis",
                    topic = self._lf_topic,
                    callback = self._lf_callback
                )
                self._lf_sub.run()

        # rpc client which resets motion controller state for each new application
        self._reset_state_sub = CommlibFactory.getSubscriber(
            broker = "redis", 
            topic = "motion_state.reset", 
            callback = self._reset_motion_state
        )   
        # start subscriptions to the recorded topics
        self._reset_state_sub.run()

    def _reset_motion_state(self, message, meta):
        self._complex_controller.reset()
        return {}

    def enable_callback(self, message, meta):
        self.info["enabled"] = True
        return {"enabled": True}

    def disable_callback(self, message, meta):
        self.info["enabled"] = False
        return {"enabled": False}

    def start(self):
        self.enable_rpc_server.run()
        self.disable_rpc_server.run()
        
        self.initializer.start()

        self.motion_calibration_server.run()
        self.move_action_server.run()
        self.lf_action_server.run()

        if self.info["mode"] == "real":
            self._motor_driver.start()

    def stop(self):
        self.enable_rpc_server.stop()
        self.disable_rpc_server.stop()

        self.motion_calibration_server.stop()
        self.move_action_server.stop()
        self.lf_action_server.stop()

        # if these subscribers are initialized, then terminate them
        if self._imu_sub is not None:
            self._imu_sub.stop()
        if self._enc_left_sub is not None:
            self._enc_left_sub.stop()
        if self._enc_right_sub is not None:
            self._enc_right_sub.stop()
        
        if self.info["mode"] == "real":
            self._motor_driver.stop()

    def on_goal_cmd_vel(self, goalh):
        self.logger.info("Robot motion started {}".format(self.name))

        self.logger.info("=========================================== {}".format(goalh.data['duration']))

        ret = self._goal_handler(goalh)
        
        self.logger.info("{} Robot motion finished".format(self.name))
        return ret

    def on_goal_follow_line(self, goalh):
        self.logger.info("Line following started {}".format(self.name))
        
        ret = self._goal_handler(goalh)

        self.logger.info("{} Line following finished".format(self.name))
        return ret
    
    def _goal_handler(self, goalh):
        # prepare response's template
        timestamp = time.time()
        secs = int(timestamp)
        nanosecs = int((timestamp-secs) * 10**(9))
        ret = {
            "header":{
                "stamp":{
                    "sec": secs,
                    "nanosec": nanosecs
                }
            }
        }
        
        # assign to the complex controller the new goal to take care of
        self._complex_controller.set_next_goal(goal=goalh.data)
        
        # get controller's internal velocities
        vels = self._complex_controller.get_velocities()

        # store velocities in persistant memory
        r = CommlibFactory.derp_client.lset(
            self.derp_data_key,
            [{
                "data": {
                    "linearVelocity": vels['linear'],
                    "rotationalVelocity": vels['rotational']
                },
                "timestamp": timestamp
            }]
        )

        # wait until complex controller finish goal or goal is cancelled
        while self._complex_controller.is_running():
            if goalh.cancel_event.is_set():
                self._complex_controller.preempt_goal()
                self.logger.info("Goal Cancelled")

                return ret
            time.sleep(0.1)


