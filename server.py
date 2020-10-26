#!/usr/bin/env python
# -*- coding: utf-8 -*-

from flask import Flask, request, jsonify
from ai import RandomStrategy, RewardMaxStrategy
from env import RecurrentEnvironment
import sys

USER = "slong"
EMAIL = "slong@veepee.com"
TAG = "MaxReward"

server = Flask("AiServer-{tag}".format(tag=TAG))

#  env = RecordEnvironement()
#  strategy = RandomStrategy(env)

GAME_DICT = {}

env = RecurrentEnvironment()
optim_strategy = RewardMaxStrategy(env)
random_strategy = RandomStrategy(env)


@server.route("/name", methods=["POST"])
def get_username():
    return jsonify(name=USER, email=EMAIL)


@server.route("/move", methods=["POST"])
def next_move():
    state = request.get_json()
    game_id = state["game"]["id"]
    if game_id not in GAME_DICT:
        env = RecurrentEnvironment()
        optim_strategy = RewardMaxStrategy(env)
        random_strategy = RandomStrategy(env)
        GAME_DICT[game_id] = {
            "env": env,
            "optim_strategy": optim_strategy,
            "fallback": random_strategy
        }
    game = GAME_DICT[game_id]
    env = game["env"]
    optim_strategy = game["optim_strategy"]
    fallback = game["fallback"]
    env.update(state)
    try:
        best_move = optim_strategy.best_action()
    except Exception:
        best_move = fallback.best_action()
    env.update_after_player_action(best_move)
    return jsonify(move=best_move)


if __name__ == '__main__':
    try:
        server.run(host="0.0.0.0", port=9090)
    finally:
        print("Save game frames and board before exiting ...")
        env.save(".")
        sys.exit(0)
