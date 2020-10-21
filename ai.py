#!/usr/bin/env python
# -*- coding: utf-8 -*-
from collections import deque
from copy import copy
from itertools import product
from random import choice
import sys

from loguru import logger

from common import FIREACTION, MOVEACTION, Enemy, Player

logger.remove()
logger.add("run.log",
           format="{time}:{level}:{line}:{function}:{message}",
           level="INFO")
#  logger.add(sys.stderr,
           #  format="{time}:{level}:{line}:{function}:{message}",
           #  level="INFO")


class Stratey:
    ALL_ACTIONS = list(MOVEACTION) + list(FIREACTION)

    def __init__(self, env):
        self.env = env

    def best_action(self):
        best = ""
        self.env.update_from_action(best)
        return best


class RandomStrategy(Stratey):
    def best_action(self):
        best = choice(Stratey.ALL_ACTIONS)
        self.env.update_from_action(best)
        return str(best)


class RewardMaxStrategy(Stratey):
    def best_action(self):
        """
        chose action that maximize actions if there is action with pos rewards
        TODO epsilon-greedy approach
        """
        agent_to_actions = self.next_actions_of_others()
        player_next_actions, _ = self.env.player.next_actions(self.env)
        # for each action of player, we calculate the expected reward
        expected_rewards = []
        for p_action in player_next_actions:
            # get all combinations of possible actions of other agents
            # assume that the equi prob of each action
            all_combs = [
                product([ag], actions)
                for ag, actions in agent_to_actions.items()
            ]
            tot_reward = 0
            tot_count = 0
            for comb in product(*all_combs):
                tot_count += 1
                agent_to_one_action = dict(comb)
                tot_reward += self.step_reward(p_action, agent_to_one_action)
            expected_rewards.append(tot_reward /
                                    tot_count if tot_count > 0 else 0)
        # chose the action that maximize the expected reward
        logger.info("Rewards of each action: {}".format(list(zip(player_next_actions, expected_rewards))))
        max_reward = max(expected_rewards)
        max_actions = [
            a for i, a in enumerate(player_next_actions)
            if expected_rewards[i] == max_reward
        ]
        if len(max_actions) == 1:
            best = str(max_actions[0])
        else:
            best = str(choice(max_actions))
        logger.info("Best action: {}".format(best))
        return best

    def next_actions_of_others(self):
        """
        All possible actions of other agents (player or enemies) in visible area

        Returns:
            agent_to_actions: dict(agent-> ([actions], [probs])
        """
        agent_to_actions = {}
        for player in self.env.other_players:
            agent_to_actions[player] = player.next_actions(self.env)[0]
        for enemy in self.env.enemies:
            agent_to_actions[enemy] = enemy.next_actions(self.env)[0]
        return agent_to_actions

    def clear_shot_moves(self,
                         player_position,
                         agents_next_position,
                         max_step=10):
        """
        Get the minimum moves between player and all other agents (other players and
        enemies.
        Here we use a simple bfs search as we can assume that the visible area is quite small
        """
        agents_to_moves = {}
        queue = deque([])
        queue.append((player_position, 0))
        seen_positions = set()

        # patch
        # remove agents pos that already collides with player position when calculate shot moves
        agents_next_position_copy = copy(agents_next_position)
        for ag, ag_pos in agents_next_position.items():
            if ag_pos == player_position:
                del agents_next_position_copy[ag]

        # if there are still agents that are not determined
        while len(queue) > 0 and len(agents_to_moves) < len(
                agents_next_position_copy):
            base_pos, step = queue.popleft()
            if step > max_step:
                break
            seen_positions.add(base_pos)

            # add next search candidates
            for action in list(MOVEACTION):
                new_pos = action.move(base_pos[0], base_pos[1])
                if self.env.valid_pos(
                        new_pos[0],
                        new_pos[1]) and new_pos not in seen_positions:
                    queue.append((new_pos, step + 1))

            # check if this new pos has a clear shot of any enemies or players
            for ag, ag_pos in agents_next_position_copy.items():
                if ag not in agents_to_moves:
                    if base_pos[0] == ag_pos[0] and base_pos[1] > ag_pos[1]:
                        if self.env.has_clear_shoot(base_pos, FIREACTION.UP,
                                                    ag_pos):
                            agents_to_moves[ag] = step
                    elif base_pos[0] == ag_pos[0] and base_pos[1] < ag_pos[1]:
                        if self.env.has_clear_shoot(base_pos, FIREACTION.DOWN,
                                                    ag_pos):
                            agents_to_moves[ag] = step
                    elif base_pos[1] == ag_pos[1] and base_pos[0] < ag_pos[0]:
                        if self.env.has_clear_shoot(base_pos, FIREACTION.RIGHT,
                                                    ag_pos):
                            agents_to_moves[ag] = step
                    elif base_pos[1] == ag_pos[1] and base_pos[0] > ag_pos[0]:
                        if self.env.has_clear_shoot(base_pos, FIREACTION.LEFT,
                                                    ag_pos):
                            agents_to_moves[ag] = step
                    else:
                        pass
        # not reacheable in max_steps
        for ag in agents_next_position_copy:
            if ag not in agents_to_moves:
                agents_to_moves[ag] = 9999
        return agents_to_moves

    def step_reward(self, player_action, agent_to_actions):
        """After knowing the next action of every agents in visible area,
        try getting the rewards

        Args:
            player_action: action taken by player
            agent_to_actions:  dict(agent -> MOVEACTION|FIREACTION) for enemies and other players
        Returns:
            reward: reward of player

        # TODO take account into the rewards of other players, try to minimize the reward of others
        """

        reward = 0
        player = self.env.player
        agents_next_position = {}
        player_next_position = None
        logger.info("===============step reward=================")
        logger.info("Player action: {}".format(player_action))
        logger.info("Agents action: {}".format(agent_to_actions))

        # ===========================================================================
        # first process player moves
        # ===========================================================================
        for agent, action in agent_to_actions.items():
            if isinstance(agent, Player):
                agents_next_position[agent] = action.move(agent.x, agent.y)
            else:
                agents_next_position[agent] = (agent.x, agent.y)
        player_next_position = action.move(player.x, player.y)

        # check if player move leads to death of player
        # i.e., overlap with other players
        collision = 0
        for p, pos in agents_next_position.items():
            if isinstance(p, Player) and pos == player_next_position:
                collision += 1
        if collision > 0:
            logger.info("Move lead to death: {} times".format(collision))
            logger.info("Reward: {}".format(-100))
            reward -= 100

        # ===========================================================================
        # then process players shoot
        # ===========================================================================
        # times of killed, killing other players and killing enemies
        killed, killed_others, killed_enemies = 0, 0, 0

        # check if killed by other players
        for agent, action in agent_to_actions.items():
            if not isinstance(action, FIREACTION):
                continue
            # check if player is killed by other players
            if self.env.has_clear_shoot(agents_next_position[agent], action,
                                        player_next_position):
                killed += 1

        # check if kill other player or enemies
        if isinstance(player_action, FIREACTION):
            for agent, pos in agents_next_position.items():
                if self.env.has_clear_shoot(player_next_position,
                                            player_action, pos):
                    if isinstance(agent, Player):
                        killed_others += 1
                    else:
                        killed_enemies += 1
        delta = (killed_others) * 150 + killed_enemies * 100
        logger.info("Kill other players:{}, enemies: {} by shooting".format(
            killed_others, killed_enemies))
        logger.info("Reward: {}".format(delta))
        reward += delta

        # ===========================================================================
        # then process enemy move
        # case 1: neutral enemy, score!
        # case 2: hostile enemy, killed!
        # ===========================================================================
        dead_times, kill_times = 0, 0
        for agent, action in agent_to_actions.items():
            if not isinstance(agent, Enemy):
                continue
            new_pos = action.move(agent.x, agent.y)
            agents_next_position[agent] = new_pos
            if new_pos == player_next_position:
                if agent.is_neutral:
                    kill_times += 1
                else:
                    dead_times += 1
        delta = int(dead_times > 0) * (-100) + kill_times * 100
        reward += delta
        logger.info("Killed by enemies: {}, kill enemies by moving: {}".format(
            dead_times, kill_times))
        logger.info("Reward: {}".format(delta))

        # ===========================================================================
        # enemy approaching reward (sometimes player chose not to move and
        # enemy can approach you if they got no other choice
        # ===========================================================================
        agents_clear_shot_moves = self.clear_shot_moves(
            player_next_position, agents_next_position)
        logger.info("player next pos: {}, agents next pos: {}".format(
            player_next_position, agents_next_position))
        logger.info("Clear shot moves: {}".format(agents_clear_shot_moves))
        delta = sum(
            map(
                lambda i: 1.0 / (i[1] + 1) * 40.0,
                filter(lambda i: isinstance(i[0], Enemy),
                       agents_clear_shot_moves.items())))
        logger.info("Clear shot reward: {}".format(delta))
        reward += delta

        # ===========================================================================
        # 1. board exploration reward: number of unknown space explored
        # 2. don't repeat the path that you already did
        # ===========================================================================
        # newly explored area
        count = self.env.added_exploration_area(player_next_position[0],
                                                player_next_position[1])
        reward += count * 2
        logger.info("New exploration area reward: {}".format(count * 2))

        # in some case, moves in all directions could lead to 0 newly space explored
        # so what should do?
        # approach: look ahead n step
        look_ahead_step = 5
        look_ahead_count = 0
        fx, fy = player_next_position[0], player_next_position[1]
        if isinstance(player_action, MOVEACTION):
            for i in range(look_ahead_step):
                fx, fy = player_action.move(fx, fy)
                if not self.env.valid_pos(fx, fy):
                    break
                look_ahead_count += self.env.added_exploration_area(fx, fy)
        reward += look_ahead_count
        logger.info("Look ahead reward: {}".format(look_ahead_count))

        history_look_ahead = 10
        repeat = 0
        # don't repeat the move that you just did in last steps
        # this help us get rid of a dead loop
        for i in range(1, min(history_look_ahead + 1,
                              len(player.positions) + 1)):
            if player_next_position == player.positions[-i]:
                repeat = i
                break
        reward -= (history_look_ahead - repeat)
        logger.info("Repeat reward: {}".format(repeat - history_look_ahead))
        return reward
