#!/usr/bin/env python
# -*- coding: utf-8 -*-

from flask import Flask, request, jsonify
from strategy.random import RandomStrategy

USER = "slong"
EMAIL = "slong@veepee.com"
ACTIONS = [
    "up", "down", "left", "right", "fire-up", "fire-down", "fire-left",
    "fire-right"
]
TAG = "Random"

server = Flask("AiServer-{tag}".format(tag=TAG))

@server.route("/name", methods=["POST"])
def get_username():
    jsonify(username=USER, email=EMAIL)


@server.route("/move", methods=["POST"])
def next_move():
    environement = request.get_json()
    move = 
    return jsonify(move=choice(ACTIONS))


if __name__ == '__main__':
    server.run(host="0.0.0.0", port=9090)
