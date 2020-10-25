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
        expected_enemy_move_combat_rewards = []
        expected_enemy_combat_approaching_rewards = []

        for p_action in player_next_actions:
            expected_move_combat_rewards.append(
                self.move_combat_reward(p_action, agents_action_to_proba))
            expected_shoot_combat_rewards.append(
                self.shoot_combat_reward(p_action, agents_action_to_proba))
            expected_enemy_move_combat_rewards.append(
                self.enemy_move_combat_reward(p_action,
                                              agents_action_to_proba))
            expected_enemy_combat_approaching_rewards.append(
                self.enemy_combat_approaching_reward(p_action,
                                                     agents_position_to_proba))

        # sum of all combat rewards
        tot_combat_rewards = [
            expected_move_combat_rewards[i] +
            expected_shoot_combat_rewards[i] +
            expected_enemy_move_combat_rewards[i] +
            expected_enemy_combat_approaching_rewards[i]
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
        action_to_combat_reward = dict(
            zip(player_next_actions, tot_combat_rewards))
        expected_exploration_rewards = []
        moves_actions = []
        for p_action in player_next_actions:
            if isinstance(p_action,
                          MOVEACTION) and p_action != MOVEACTION.INVALID:
                new_pos = p_action.move(self.env.player.x, self.env.player.y)
                #  reward = self.visible_area_reward(new_pos)
                reward = self.exploration_reward(new_pos)
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

    def moves_to_target(self, player_position, target_positions, max_step=12):
        """
        Get the minimum moves between player and all other target positions.
        Here we use a simple bfs search as we can assume that the visible area is quite small

        Note: during the bfs search, all cells excepted WALL are considered (known and unknown)
        are considering <FREE> cell that the player can <move to> and <shoot through>

        Args:
            player_position (tuple(x, y)): player current positions
            target_positions (list(tuple)): list of target positions
            max_step (int): max bfs search steps

        Return:
            positions_to_shot_moves (dict): {target_position -> number of moves to get a shot of enemy}
            positions_to_move (dict): {target_position -> number of moves to touch enemy}
        """
        positions_to_shot_moves = {}
        positions_to_move = {}
        queue = deque([])
        queue.append((player_position, 0))
        seen_positions = set()

        # if there are still agents that are not determined
        while len(queue) > 0 and len(positions_to_move) < len(
                target_positions):
            base_pos, step = queue.popleft()
            if step > max_step:
                continue
            seen_positions.add(base_pos)

            # add next search candidates
            for action in list(MOVEACTION):
                new_pos = action.move(base_pos[0], base_pos[1])
                # unknown cell is a valid pos too!
                if self.env.valid_pos(
                        new_pos[0],
                        new_pos[1]) and new_pos not in seen_positions:
                    queue.append((new_pos, step + 1))

            for pos in target_positions:
                # check if this new pos has a clear shot of target pos
                if pos not in positions_to_shot_moves:
                    if base_pos[0] == pos[0] and base_pos[1] > pos[1]:
                        if self.env.can_shoot(base_pos, FIREACTION.UP, pos):
                            positions_to_shot_moves[pos] = step
                    elif base_pos[0] == pos[0] and base_pos[1] < pos[1]:
                        if self.env.can_shoot(base_pos, FIREACTION.DOWN, pos):
                            positions_to_shot_moves[pos] = step
                    elif base_pos[1] == pos[1] and base_pos[0] < pos[0]:
                        if self.env.can_shoot(base_pos, FIREACTION.RIGHT, pos):
                            positions_to_shot_moves[pos] = step
                    elif base_pos[1] == pos[1] and base_pos[0] > pos[0]:
                        if self.env.can_shoot(base_pos, FIREACTION.LEFT, pos):
                            positions_to_shot_moves[pos] = step
                    else:
                        pass
                # check if the new pos can reach the target pos
                if pos not in positions_to_move:
                    if base_pos == pos:
                        positions_to_move[pos] = step

        # not reacheable in max_steps
        #  for pos in positions_to_shot_moves:
        #  if pos not in positions_to_shot_moves:
        #  positions_to_shot_moves[pos] = 999999
        #  for pos in positions_to_move:
        #  if pos not in positions_to_shot_moves:
        #  positions_to_move[pos] = 999999
        return positions_to_shot_moves, positions_to_move

    def move_combat_reward(self, player_action, agents_action_to_proba):
        """ After knowning the next actions of all agents and the corresponding
        probabilities, calculate the expected rewards if player takes a next action.
        This will consider the following situations:
            - move leads to overlapping with other players: penalty
            - move leads to overlapping with a neutral enemies: rewards
            - move leads to overlapping with a hostile enemies: rewards
        Note when processing the kill of enemies, we should not take into account
        into the next actions taken by the enemy because the server process player move
        first.

        Args:
            player_action: next action taken by player
            agents_action_to_proba: <agents => (actions, probas)> mapping

        Return:
            reward: expected rewards
        """
        player_position = player_action.move(self.env.player.x,
                                             self.env.player.y)
        logger.info(
            "==[Move combat reward] player action: {}, player position: {}==".
            format(str(player_action), player_position))
        reward = 0
        killed_by_others, killed_by_enemies, kill_enemies = 0, 0, 0
        for agent, acts_to_prob in agents_action_to_proba.items():
            if isinstance(agent, Enemy) and agent.is_neutral:
                if player_position == (agent.x, agent.y):
                    kill_enemies += 1
            elif isinstance(agent, Enemy) and (not agent.is_neutral):
                if player_position == (agent.x, agent.y):
                    killed_by_enemies += 1
            else:
                for act, proba in zip(*acts_to_prob):
                    if player_position == act.move(agent.x, agent.y):
                        killed_by_others += proba
        logger.info(
            "Killed_by_others: {}, killed_by_enemies: {}, kill_enemies: {}".
            format(killed_by_others, killed_by_enemies, kill_enemies))
        reward = (killed_by_enemies +
                  killed_by_others) * (-1500) + kill_enemies * 1500
        logger.info("Final move combat: {}".format(reward))
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
        logger.info(
            "==[Shoot combat reward] player action: {}, player position: {}==".
            format(str(player_action), player_position))

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
                if isinstance(player_action, FIREACTION) and isinstance(
                        agent, Player):
                    if self.env.can_shoot(player_position, player_action,
                                          agents_next_position):
                        kill_others += proba
        logger.info("Killed: {}, kill_others: {}, kill_enemies: {}".format(
            killed, kill_others, kill_enemies))
        reward = killed * (-1500) + kill_enemies * 500 + kill_others * 750
        logger.info("Final shoot reward:{}".format(reward))
        return reward

    def enemy_move_combat_reward(self, player_action, agents_action_to_proba):
        """
        After processing player moves, player shot, we then process the enemies moves.
        If the player next position overlaps with the next position of an enemey, it
        could be killed or kill the enemy

        Note: we have to first remove the enemy that can already be killed by the player
        action in previous step, e.g., if a player fire-right action can already kill
        the enemy if `shoot_combat_reward`, we shouldn't consider the enemy move combat reward
        because it's already dead
        """
        player_position = player_action.move(self.env.player.x,
                                             self.env.player.y)
        logger.info(
            "==[Enemy move combat reward] player action: {}, player position: {}=="
            .format(str(player_action), player_position))
        reward = 0
        kill_enemies, killed = 0, 0
        for agent, acts_to_prob in agents_action_to_proba.items():
            if not isinstance(agent, Enemy):
                continue
            # Enemy is already killed by player move
            if player_position == (agent.x, agent.y) and agent.is_neutral:
                continue

            # Enemy is already killed by player shoot
            if isinstance(player_action, FIREACTION) and self.env.can_shoot(
                    player_position, player_action, (agent.x, agent.y)):
                continue

            for act, proba in zip(*acts_to_prob):
                if player_position == act.move(agent.x, agent.y):
                    if agent.is_neutral:
                        kill_enemies += proba
                    else:
                        killed += proba

        logger.info("Killed: {}, kill_enemies: {}".format(
            killed, kill_enemies))
        reward = killed * (-1500) + kill_enemies * 1500
        logger.info("Final enemy move combat reward:{}".format(reward))
        return reward

    def enemy_combat_approaching_reward(self, player_action,
                                        enemies_positions_to_prob):
        """
        Here, we consider the rewards that player action leads to approaching
        enemies in visible area.
        There are two different approaching rewards:
            - number of moves of player needs that it can get a clear shot of the enemy
            - number of moves of player needs that it can touch the enemy

        Note: we have to first remove the enemy that can already be killed by the player
        action in previous step, e.g., if a player fire-right action can already kill
        the enemy if `shoot_combat_reward`, since the enemy is alread dead, we shouldn'the
        take into account the approaching gain.
        """
        player_position = player_action.move(self.env.player.x,
                                             self.env.player.y)
        logger.info(
            "==[Enemy approaching reward] player action: {}, player position: {}=="
            .format(str(player_action), player_position))
        # first, remove enemy that are already dead by player action
        all_enemies = list(enemies_positions_to_prob.keys())
        for enemy in all_enemies:
            if isinstance(player_action, MOVEACTION):
                if player_position == (enemy.x, enemy.y) and enemy.is_neutral:
                    del enemies_positions_to_prob[enemy]
            elif isinstance(player_action, FIREACTION):
                if self.env.can_shoot(player_position, player_action,
                                      (enemy.x, enemy.y)):
                    del enemies_positions_to_prob[enemy]
            else:
                pass

        all_target_positions = set()
        for positions, _ in enemies_positions_to_prob.values():
            all_target_positions.update(positions)
        positions_to_shot_moves, positions_to_move = self.moves_to_target(
            player_position, all_target_positions)
        reward = 0
        shot_approaching_reward, touch_approaching_reward = 0, 0
        for enemy, pos_to_proba in enemies_positions_to_prob.items():
            for pos, proba in zip(*pos_to_proba):
                if pos in positions_to_shot_moves:
                    moves_to_shot = positions_to_shot_moves[pos]
                    # moves to shot is smaller, the reward is larger
                    shot_approaching_reward += 1 / (moves_to_shot +
                                                    1.0) * proba * 100
                if pos in positions_to_move:
                    moves_to_touch = positions_to_move[pos]
                    touch_approaching_reward += 1 / (moves_to_touch +
                                                     1.0) * proba * 50
        reward = shot_approaching_reward + touch_approaching_reward
        logger.info(
            "Enemy shot approaching reward:{}".format(shot_approaching_reward))
        logger.info("Enemy touch approaching reward:{}".format(
            touch_approaching_reward))
        logger.info("Final enemy approaching reward:{}".format(reward))
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

        exploration = {"unknown": 0, "known": 0, "heat": 0}
        while len(positions_to_visit) > 0:
            (x, y), current_step = positions_to_visit.popleft()
            if (x, y) in seen_positions:
                continue
            seen_positions.add((x, y))
            if self.env.board[y][x] == BoardState.FREE:
                exploration["heat"] += min(20, self.env.board_heatmap[y][x])
                exploration["known"] += 1
            elif self.env.board[y][x] == BoardState.UNKNOWN:
                exploration["heat"] += 20
                exploration["unknown"] += 1
            else:
                pass

            # if reach max step or the current pos is unknown, don't continue
            if current_step + 1 > self.env.exploration_max_step or self.env.board[
                    y][x] == BoardState.UNKNOWN:
                continue
            # add next pos that are not already seen and invalid
            for action in list(MOVEACTION):
                nx, ny = action.move(x, y)
                if (nx, ny) not in seen_positions and self.env.valid_pos(
                        nx, ny):
                    positions_to_visit.append(((nx, ny), current_step + 1))
        logger.info("Exploration statistics: {}".format(exploration))
        # calculate exploration reward
        reward = exploration["heat"]
        logger.info("Final exploration reward: {}".format(reward))
        return reward
