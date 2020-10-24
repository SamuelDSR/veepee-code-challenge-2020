#!/usr/bin/env python
# -*- coding: utf-8 -*-
from collections import deque
from random import choice

from loguru import logger

from common import FIREACTION, MOVEACTION, BoardState, Enemy, Player

logger.remove()
logger.add("run.log",
           format="{time}:{level}:{line}:{function}:{message}",
           level="INFO")
#  logger.add(sys.stderr,
#  format="{time}:{level}:{line}:{function}:{message}",
#  level="INFO")

ACTION_TO_PRIORITY = {
    MOVEACTION.UP: 10,
    MOVEACTION.DOWN: 10,
    MOVEACTION.LEFT: 10,
    MOVEACTION.RIGHT: 10,
    MOVEACTION.INVALID: 9,
    FIREACTION.LEFT: 1,
    FIREACTION.RIGHT: 1,
    FIREACTION.UP: 1,
    FIREACTION.DOWN: 1
}


def select_max(actions, rewards, priorites):
    """
    Return action with max rewards, if there are
    many optimal actions, chose the one with highest
    priorites

    Args:
        actions(list): actions list
        rewards(list): rewards list
        priorites(dict):  map(action -> priority)

    Returns:
        best: best action with max rewards and highest priority
        reward: max reward
    """
    act_reward_prio = zip(actions, zip(rewards, priorites))
    best_choice = max(act_reward_prio, key=lambda x: x[1])
    return best_choice[0], best_choice[1][0]


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
        chose the action that maximize rewards
        #TODO epsilon-greedy approach
        """
        current_player = self.env.player
        player_next_actions, _ = current_player.next_actions(self.env)
        player_actions_prios = [
            ACTION_TO_PRIORITY[action] for action in player_next_actions
        ]
        agents_action_to_proba = self.next_actions_of_others()
        agents_position_to_proba = self.next_positions_of_others()

        # for each action of player, we calculate the expected combat reward
        expected_move_combat_rewards = []
        expected_shoot_combat_rewards = []
        expected_enemy_approach_rewards = []
        for p_action in player_next_actions:
            expected_move_combat_rewards.append(
                self.move_combat_reward(p_action, agents_action_to_proba))
            expected_shoot_combat_rewards.append(
                self.shoot_combat_reward(p_action, agents_action_to_proba))
            expected_enemy_approach_rewards.append(
                self.enemy_approaching_reward(p_action,
                                              agents_position_to_proba))

        # sum of all combat rewards
        tot_combat_rewards = [
            expected_move_combat_rewards[i] +
            expected_shoot_combat_rewards[i] +
            expected_enemy_approach_rewards[i]
            for i in range(len(player_next_actions))
        ]

        # first: chose the action that maximize the expected combat reward
        # combat first!
        logger.info("Combat Rewards of each action: {}".format(
            list(zip(player_next_actions, tot_combat_rewards))))
        best_action, max_reward = select_max(player_next_actions,
                                             tot_combat_rewards,
                                             player_actions_prios)
        if max_reward > 0:
            logger.info(
                "Best action: {} selected using combat reward: {}".format(
                    max_reward, str(best_action)))
            return str(best_action)

        # if there is no combat reward, then look into exploration
        # for each position, we calculate the exploration gain
        action_to_combat_reward = dict(zip(player_next_actions, tot_combat_rewards))
        expected_exploration_rewards = []
        moves_actions = []
        for p_action in player_next_actions:
            if isinstance(p_action,
                          MOVEACTION) and p_action != MOVEACTION.INVALID:
                new_pos = p_action.move(self.env.player.x, self.env.player.y)
                reward = self.visible_area_reward(new_pos)
                reward += self.exploration_reward(new_pos)
                # add move combat to exploration to prevent agent selects a action
                # that has negative combat rewards, e.g., death of player
                reward += action_to_combat_reward[p_action]
                expected_exploration_rewards.append(reward)
                moves_actions.append(p_action)

        best_action, max_reward = select_max(moves_actions,
                                             expected_exploration_rewards,
                                             player_actions_prios)
        logger.info(
            "Best action: {} selected using exploration reward: {}".format(
                max_reward, str(best_action)))
        return str(best_action)

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

    def next_positions_of_others(self):
        """
        All possible positions of other agents (player or enemies) in visible area
        Returns:
            agent_to_positions: dict(agent-> ([positions], [probs])
        """
        agent_to_positions = {}
        for player in self.env.other_players:
            agent_to_positions[player] = player.next_positions(self.env)
        for enemy in self.env.enemies:
            agent_to_positions[enemy] = enemy.next_positions(self.env)
        return agent_to_positions

    def clear_shot_moves(self, player_position, target_positions, max_step=10):
        """
        Get the minimum moves between player and all other target positions.
        Here we use a simple bfs search as we can assume that the visible area is quite small
        """
        positions_to_moves = {}
        queue = deque([])
        queue.append((player_position, 0))
        seen_positions = set()

        # if there are still agents that are not determined
        while len(queue) > 0 and len(positions_to_moves) < len(
                target_positions):
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

            # check if this new pos has a clear shot of target pos
            for pos in target_positions:
                if pos not in positions_to_moves:
                    if base_pos[0] == pos[0] and base_pos[1] > pos[1]:
                        if self.env.can_shoot(base_pos, FIREACTION.UP, pos):
                            positions_to_moves[pos] = step
                    elif base_pos[0] == pos[0] and base_pos[1] < pos[1]:
                        if self.env.can_shoot(base_pos, FIREACTION.DOWN, pos):
                            positions_to_moves[pos] = step
                    elif base_pos[1] == pos[1] and base_pos[0] < pos[0]:
                        if self.env.can_shoot(base_pos, FIREACTION.RIGHT, pos):
                            positions_to_moves[pos] = step
                    elif base_pos[1] == pos[1] and base_pos[0] > pos[0]:
                        if self.env.can_shoot(base_pos, FIREACTION.LEFT, pos):
                            positions_to_moves[pos] = step
                    else:
                        pass
        # not reacheable in max_steps
        for pos in positions_to_moves:
            if pos not in positions_to_moves:
                positions_to_moves[pos] = 9999
        return positions_to_moves

    def move_combat_reward(self, player_action, agents_action_to_proba):
        """ After knowning the next actions of all agents and the corresponding
        probabilities, calculate the expected rewards if player takes a next action.
        This will consider the following situations:
            - move leads to overlapping with other players: penalty
            - move leads to overlapping with a neutral enemies: rewards
            - move leads to overlapping with a hostile enemies: rewards

        Args:
            player_action: next action taken by player
            agents_action_to_proba: <agents => (actions, probas)> mapping

        Return:
            reward: expected rewards
        """
        player_position = player_action.move(self.env.player.x,
                                             self.env.player.y)
        reward = 0
        for agent, acts_to_prob in agents_action_to_proba.items():
            for act, proba in zip(*acts_to_prob):
                if player_position == act.move(agent.x, agent.y):
                    if isinstance(agent, Player):
                        logger.info(
                            "Next player postion {} overlap with a player".
                            format(player_position))
                        reward += (-1500) * proba
                    elif isinstance(agent, Enemy) and agent.is_neutral:
                        logger.info(
                            "Next player postion {} overlap with a neutral enemy"
                            .format(player_position))
                        reward += 1000 * proba
                    else:
                        logger.info(
                            "Next player postion {} overlap with a hostile enemy"
                            .format(player_position))
                        reward += (-1500) * proba
        logger.info(
            "Final move combat reward:{}, player next action:{}, next pos:{}".
            format(reward, player_action, player_position))
        return reward

    def shoot_combat_reward(self, player_action, agents_action_to_proba):
        """
        Here, we process all shot and then calculate the expected shoot rewards,
        This will consider the following situations:
            - player shoot some enemies (enemies can not dodge)
            - player shoot other players
            - player is shoot by other players
        """
        player_position = player_action.move(self.env.player.x,
                                             self.env.player.y)
        # note, all the three are expected times
        killed, kill_others, kill_enemies = 0, 0, 0

        # check if kill enemies, there is no proba since enemies cannot dodge
        if isinstance(player_action, FIREACTION):
            for agent in agents_action_to_proba:
                if isinstance(agent, Enemy):
                    if self.env.can_shoot(player_position, player_action,
                                          (agent.x, agent.y)):
                        kill_enemies += 1

        for agent, acts_to_prob in agents_action_to_proba.items():
            for action, proba in zip(*acts_to_prob):
                agents_next_position = action.move(agent.x, agent.y)

                # first check if killed by other players
                if isinstance(action, FIREACTION):
                    if self.env.can_shoot(agents_next_position, action,
                                          player_position):
                        killed += proba

                # then, check if player can kill other player
                if isinstance(player_action, FIREACTION) and isinstance(agent, Player):
                    if self.env.can_shoot(player_position, player_action,
                                          agents_next_position):
                        kill_others += proba
        logger.info("Expectance of player getting killed: {}".format(killed))
        logger.info("Expectance of player killing others players: {}".format(
            kill_others))
        logger.info(
            "Expectance of player killing enemies: {}".format(kill_enemies))
        reward = killed * (-1500) + kill_enemies * 500 + kill_others * 700
        logger.info(
            "Final shoot reward:{}, player next action: {}, next pos: {}".
            format(reward, player_action, player_position))
        return reward

    def enemy_approaching_reward(self, player_action,
                                 enemies_positions_to_prob):
        """
        Here, we consider the rewards that player action leads to approaching
        enemies in visible area.
        The approaching reward is not based how far the distance between
        the player and enemy, it's based that how many moves that the player
        needs to get a shoot of position that enemy occupies.

        """
        player_position = player_action.move(self.env.player.x,
                                             self.env.player.y)
        reward = 0
        all_target_positions = set()
        for positions, _ in enemies_positions_to_prob.values():
            all_target_positions.update(positions)
        positions_to_moves = self.clear_shot_moves(player_position,
                                                   all_target_positions)

        for enemy, pos_to_proba in enemies_positions_to_prob.items():
            for pos, proba in zip(*pos_to_proba):
                if pos in positions_to_moves:
                    moves_to_shot = positions_to_moves[pos]
                    # moves to shot is smaller, the reward is larger
                    reward += 1 / (moves_to_shot + 1.0) * proba * 100
        logger.info(
            "Final enemy approaching reward:{}, player next action: {}, next pos: {}"
            .format(reward, player_action, player_position))
        return reward

    def visible_area_reward(self, position):
        """number of added unknown space could be explored in this position
        """
        added_area = self.env.added_exploration_area(position[0], position[1])
        reward = added_area * 20
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

        steps_to_test = [4, 8, 12]
        max_step = max(steps_to_test)
        exploration = {}
        for s in steps_to_test:
            exploration[s] = {"unknown": 0, "known": 0, "heat": 0}
        while len(positions_to_visit) > 0:
            (x, y), current_step = positions_to_visit.popleft()
            if (x, y) in seen_positions:
                continue
            seen_positions.add((x, y))

            if self.env.board[y][x] == BoardState.FREE:
                for s, stat in exploration.items():
                    if current_step <= s:
                        stat["heat"] += min(5, self.env.board_heatmap[y][x])
                        stat["known"] += 1
            elif self.env.board[y][x] == BoardState.UNKNOWN:
                for s, stat in exploration.items():
                    if current_step <= s:
                        stat["unknown"] += 1
                        stat["heat"] += 5
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
            #  exploration[s]["known"] + exploration[s]["unknown"] * 2
            exploration[s]["heat"] for s in steps_to_test
        ]
        logger.info("Exploration reward for steps: {}".format(step_rewards))
        exploration_reward, last_r = 0, 0
        alpha = 0.75
        for i, r in enumerate(step_rewards):
            exploration_reward += (r - last_r) * alpha**i
            last_r = r
        logger.info("Final exploration reward: {}".format(exploration_reward))
        return exploration_reward
