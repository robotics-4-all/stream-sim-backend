#!/usr/bin/python
# -*- coding: utf-8 -*-

import time
import json
import yaml
import numpy
import logging

from commlib.logger import Logger

from .conn_params import ConnParams
if ConnParams.type == "amqp":
    from commlib.transports.amqp import Publisher
elif ConnParams.type == "redis":
    from commlib.transports.redis import Publisher

class World:
    def __init__(self):
        self.logger = Logger("world")

    def load_file(self, filename = None):
        with open(filename, 'r') as stream:
            try:
                self.world = yaml.safe_load(stream)
                self.logger.info("World loaded")
                self.setup()
            except yaml.YAMLError as exc:
                self.logger.critical("World filename does not exist")

    def from_configuration(self, configuration = None):
        self.world = configuration
        self.logger.info("World loaded")
        self.setup()

    def setup(self):

        # Publishers
        # self.world_pub = Publisher(conn_params=ConnParams.get("redis"), topic= "world:details")
        # self.world_pub.publish(self.world)

        self.width = self.world['map']['width']
        self.height = self.world['map']['height']

        self.map = numpy.zeros((self.width, self.height))
        self.resolution = self.world['map']['resolution']

        # Add obstacles information in map
        self.obstacles = self.world['map']['obstacles']['lines']
        for obst in self.obstacles:
            x1 = obst['x1']
            x2 = obst['x2']
            y1 = obst['y1']
            y2 = obst['y2']
            if x1 == x2:
                if y1 > y2:
                    tmp = y2
                    y2 = y1
                    y1 = tmp
                for i in range(y1, y2 + 1):
                    self.map[x1, i] = 1
            elif y1 == y2:
                if x1 > x2:
                    tmp = x2
                    x2 = x1
                    x1 = tmp
                for i in range(x1, x2 + 1):
                    self.map[i, y1] = 1
