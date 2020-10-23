#!/usr/bin/env python
# -*- coding: utf-8 -*-
from collections import deque
from copy import copy
from itertools import product
from random import choice

from loguru import logger

from common import FIREACTION, MOVEACTION, Enemy, Player, BoardState

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
    @logger.catch
    def best_action(self):
        """
        chose action that maximize actions if there is action with pos rewards
        TODO epsilon-greedy approach
        """
        agent_to_actions = self.next_actions_of_others()
        player_next_actions = self.env.player.next_actions(self.env)

        combinations = 1
        for p, acts in agent_to_actions.items():
            combinations *= len(acts)
        combinations *= len(player_next_actions)
        logger.info("Number of combinations: {}".format(combinations))

        # for each action of player, we calculate the expected combat reward
        expected_combat_rewards = []
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
                tot_reward += self.combat_reward(p_action, agent_to_one_action)
            expected_combat_rewards.append(tot_reward /
                                           tot_count if tot_count > 0 else 0)

        # for each position, we calculate the exploration gain
        expected_exploration_rewards = []
        for p_action in player_next_actions:
            new_pos = p_action.move(self.env.player.x, self.env.player.y)
            reward = self.visible_area_reward(new_pos)
            reward += self.exploration_reward(new_pos)
            expected_exploration_rewards.append(reward)

        # sum of the two kinds of rewards
        expected_rewards = [
            x + y for x, y in zip(expected_combat_rewards,
                                  expected_exploration_rewards)
        ]

        # chose the action that maximize the expected reward
        logger.info("Rewards of each action: {}".format(
            list(zip(player_next_actions, expected_combat_rewards))))
        max_reward = max(expected_rewards)
        max_actions = [
            a for i, a in enumerate(player_next_actions)
            if expected_rewards[i] == max_reward
        ]
        if len(max_actions) == 1:
            best = str(max_actions[0])
        else:
            # priority of actions in case equal rewards, e.g., invalid precedes shoot
            # move precedes invalid
            best = None
            moves_actions = [
                a for a in max_actions if isinstance(a, MOVEACTION)
            ]
            if len(moves_actions) > 0:
                best = str(choice(moves_actions))
            if best is None:
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
            agent_to_actions[player] = player.next_actions(self.env)
        for enemy in self.env.enemies:
            agent_to_actions[enemy] = enemy.next_actions(self.env)
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
                        if self.env.can_shoot(base_pos, FIREACTION.UP, ag_pos):
                            agents_to_moves[ag] = step
                    elif base_pos[0] == ag_pos[0] and base_pos[1] < ag_pos[1]:
                        if self.env.can_shoot(base_pos, FIREACTION.DOWN,
                                              ag_pos):
                            agents_to_moves[ag] = step
                    elif base_pos[1] == ag_pos[1] and base_pos[0] < ag_pos[0]:
                        if self.env.can_shoot(base_pos, FIREACTION.RIGHT,
                                              ag_pos):
                            agents_to_moves[ag] = step
                    elif base_pos[1] == ag_pos[1] and base_pos[0] > ag_pos[0]:
                        if self.env.can_shoot(base_pos, FIREACTION.LEFT,
                                              ag_pos):
                            agents_to_moves[ag] = step
                    else:
                        pass
        # not reacheable in max_steps
        for ag in agents_next_position_copy:
            if ag not in agents_to_moves:
                agents_to_moves[ag] = 9999
        return agents_to_moves

    def combat_reward(self, player_action, agent_to_actions):
        """After knowing the next action of every agents in visible area,
        return the reward of the action

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
        logger.info("===============combat reward=================")
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
        player_next_position = player_action.move(player.x, player.y)

        # check if player move leads to death of player
        # i.e., overlap with other players
        collision = 0
        for p, pos in agents_next_position.items():
            if isinstance(p, Player) and pos == player_next_position:
                collision += 1
        if collision > 0:
            logger.info("Move lead to death: {} times, reward: {}".format(
                collision, -1500))
            reward -= 1500

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
            if self.env.can_shoot(agents_next_position[agent], action,
                                  player_next_position):
                killed += 1

        # check if kill other player or enemies
        if isinstance(player_action, FIREACTION):
            for agent, pos in agents_next_position.items():
                if self.env.can_shoot(player_next_position, player_action,
                                      pos):
                    if isinstance(agent, Player):
                        killed_others += 1
                    else:
                        killed_enemies += 1
        # reward by shoot should be penalized against touching due to shoot cd
        delta = killed_others * 500 + killed_enemies * 500
        if killed > 0:
            delta -= 500
        logger.info(
            "Killed by others: {}, Kill other players:{}, enemies: {} by shooting, reward: {}"
            .format(killed, killed_others, killed_enemies, delta))
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
        delta = int(dead_times > 0) * (-1500) + kill_times * 1000
        reward += delta
        logger.info(
            "Killed by enemies: {}, kill enemies by moving: {}, reward: {}".
            format(dead_times, kill_times, delta))

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
                lambda i: 1.0 / (i[1] + 1) * 200.0,
                filter(lambda i: isinstance(i[0], Enemy),
                       agents_clear_shot_moves.items())))
        logger.info("Clear shot reward: {}".format(delta))
        reward += delta
        return reward

    def visible_area_reward(self, position):
        """number of added unknown space could be explored in this position
        """
        added_area = self.env.added_exploration_area(position[0], position[1])
        reward = added_area * 5
        logger.info("New exploration area: {}, reward: {}".format(
            added_area, reward))
        return reward

    def exploration_reward(self, position):
        """
        From the base pos, do a breadth-first walk of the current board within max steps
        Idea: the exploration reward for a position (x, y) is:
            - the number of known positions it can visite with max_step steps
            - the number of (unknown positions)*2 it can reach
        """
        seen_positions = set()
        step = 0
        positions_to_visit = deque([])
        positions_to_visit.append((position, step))

        steps_to_test = [4, 8]
        max_step = max(steps_to_test)
        exploration = {}
        for s in steps_to_test:
            exploration[s] = {"known": 0, "unknown": 0}
        while len(positions_to_visit) > 0:
            (x, y), current_step = positions_to_visit.popleft()
            if (x, y) in seen_positions:
                continue
            seen_positions.add((x, y))

            if self.env.board[y][x] == BoardState.FREE:
                for s, stat in exploration.items():
                    if current_step <= s:
                        stat["known"] += 1
            elif self.env.board[y][x] == BoardState.UNKNOWN:
                for s, stat in exploration.items():
                    if current_step <= s:
                        stat["unknown"] += 1
            else:
                pass

            # if reach max step or the current pos is unknown, don't continue
            if current_step + 1 > max_step or self.env.board[y][
                    x] == BoardState.UNKNOWN:
                continue
            # add next pos that are not already seen and invalid
            for action in list(MOVEACTION):
                nx, ny = action.move(x, y)
                if (nx, ny) not in seen_positions and self.env.valid_pos(
                        nx, ny):
                    positions_to_visit.append(((nx, ny), current_step + 1))

        logger.info("Exploration statistics: {}".format(exploration))
        # calculate exploration reward
        step_rewards = [
            exploration[s]["known"] + exploration[s]["unknown"] * 2
            for s in steps_to_test
        ]
        logger.info("Exploration reward for steps: {}".format(step_rewards))
        exploration_reward, last_r = 0, 0
        alpha = 0.8
        for i, r in enumerate(step_rewards):
            exploration_reward += (r - last_r) * alpha**i
            last_r = r
        logger.info("Final exploration reward: {}".format(exploration_reward))
        return exploration_reward
