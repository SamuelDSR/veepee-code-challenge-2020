#!/usr/bin/env python
# -*- coding: utf-8 -*-

from flask import Flask, request, jsonify
from ai import RandomStrategy, RewardMaxStrategy
from env import RecurrentEnvironment, RecordEnvironement

USER = "slong"
EMAIL = "slong@veepee.com"
TAG = "MaxReward"

server = Flask("AiServer-{tag}".format(tag=TAG))

#  env = RecordEnvironement()
#  strategy = RandomStrategy(env)

env = RecurrentEnvironment()
optim_strategy = RewardMaxStrategy(env)
random_strategy = RandomStrategy(env)

@server.route("/name", methods=["POST"])
def get_username():
    return jsonify(name=USER, email=EMAIL)


@server.route("/move", methods=["POST"])
def next_move():
    state = request.get_json()
    env.update(state)
    try:
        best_move = optim_strategy.best_action()
    except Exception:
        best_move = random_strategy.best_action()
    env.update_after_player_action(best_move)
    env.save_frame(".")
    return jsonify(move=best_move)


if __name__ == '__main__':
    server.run(host="0.0.0.0", port=9090)
