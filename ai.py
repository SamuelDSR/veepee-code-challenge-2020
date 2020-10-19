#!/usr/bin/env python
# -*- coding: utf-8 -*-
from random import choice
from common import MOVEACTION, FIREACTION, Player, Enemy


class Stratey:
    ALL_ACTIONS = list(MOVEACTION) + list(FIREACTION)

    def __init__(self, env):
        self._env = env

    def best_action(self):
        pass


class RandomStrategy(Stratey):
    def best_action(self):
        return choice(Stratey.ALL_ACTIONS)


class RewardMaxStrategy(Stratey):
    def __init__(self, env):
        super().__init__(env)

    def best_action(self):
        rewards = []
        for action in Stratey.ALL_ACTIONS:
            reward = self.evalute_action(action)
            rewards.append(reward)
        # chose action that maximize actions if there is action with pos rewards
        # or using a epsilon-greedy approach
        # TODO

    def next_actions_of_others(self):
        """
        All possible actions of other agents (player or enemies) in visible area

        Returns:
            agent_to_actions: dict(agent-> ([actions], [probs])
        """
        agent_to_actions = {}
        for player in self.other_players:
            agent_to_actions[player] = player.next_actions(self.env)
        for enemy in self.env.enemies:
            agent_to_actions[enemy] = enemy.next_actions(self.env)
        return agent_to_actions

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
            if self.env.has_clear_shoot(agents_next_position[agent],
                                        action, player_next_position):
                killed += 1

        # check if kill other player or enemies
        if isinstance(player_action, FIREACTION):
            for agent, pos in agents_next_position:
                if self.env.has_clear_shoot(player_next_position, player_action, pos):
                    if isinstance(agent, Player):
                        killed_others += 1
                    else:
                        killed_enemies += 1
        reward += (killed_others) * 150 + killed_enemies * 100

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
        reward += int(dead_times > 0) * (-100) + kill_times * 100

        # ===========================================================================
        # enemy appraoching reward
        # ===========================================================================

        # ===========================================================================
        # board exploration reward
        # ===========================================================================
