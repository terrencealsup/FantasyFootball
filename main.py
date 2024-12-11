import numpy as np
import json 
import sys


class League:

    def __init__(self, schedule, points):

        # Get the participants and number of participants
        self.participants = list(schedule.keys())
        self.n = len(self.participants)

        # Get the actual play schedule and points scored each week
        self.schedule = schedule
        self.points = points

        # Number of weeks
        self.n_weeks = max(len(self.points[p]) for p in self.participants)

        # Set the total points for each player
        self.total_points = {p: sum(self.points[p]) for p in self.participants}

        # Set cutoff rank for last playoff spot
        self.cutoff = self.n // 2

        # Set mappings for team names to ids and vice versa
        self.id_to_team = {i: self.participants[i] for i in range(self.n)}
        self.team_to_id = {self.id_to_team[i]:i for i in self.id_to_team.keys()}

        # Get actual ranks and wins based on provided schedule and points
        # Determine number of wins based on the actual schedule provided
        self.wins = self.get_wins_from_schedule()
        self.ranks = self.get_ranks_from_wins_points(self.wins, self.total_points)

    
    def get_wins_from_schedule(self):
        wins = {}
        for p in self.participants:
            num_wins = 0
            for week in range(self.n_weeks):
                # Get the opponent
                opp = self.schedule[p][week%(self.n-1)]

                isWin = 1 if self.points[p][week] >= self.points[opp][week] else 0

                num_wins += isWin 
            
            wins[p] = num_wins
        return wins


    def get_ranks_from_wins_points(self, wins, total_points):

        df = np.rec.fromrecords(
            [(p, wins[p], total_points[p]) for p in self.participants], 
            dtype=[("participant", "U32"), ("wins", int), ("points", float)]
        )
        ix = np.argsort(df, order=['wins', 'points'])
        ranks = {self.participants[ix[i]]: self.n-i for i in range(self.n)}
        return ranks

    
    def sample_permutation(self):
        return np.append(np.random.permutation(self.n-1), self.n-1)


    def get_opponent_for_week(self, i, week):
        """
        Return the index corresponding to the opponent of team i on week with n players.
        See https://en.wikipedia.org/wiki/Round-robin_tournament
        
        Assume n is even, 0 <= i <= n-1, and 0 <= week < num_weeks

        Last value stays fixed when rotating clockwise, e.g. n=7
        0 1 2 3  ->  6 0 1 2  ->  5 6 0 1    etc.
        7 6 5 4      7 5 4 3      7 4 3 2
        """
        r = week % (self.n-1)  # Opponents restart after everyone has been faced
        
        if i == self.n-1:
            pos = self.n-1
        else:
            pos = (i + r) % (self.n-1)

        opos = self.n-1 - pos

        if opos == self.n-1:
            return self.n-1
        else:
            return (opos - r) % (self.n-1)


    def simulate_schedule(self, permutation):
        # Get mappings for the permuted team ids
        team_to_perm_id = {self.participants[i]: permutation[i] for i in range(self.n)}
        perm_id_to_team = {team_to_perm_id[i]: i for i in team_to_perm_id.keys()}

        wins = {p:0 for p in self.participants}
        for p in self.participants:
            team_id = team_to_perm_id[p]
            num_wins = 0
            for week in range(self.n_weeks):
                # Get the opponent
                oppo = perm_id_to_team[self.get_opponent_for_week(team_id, week)]
        
                isWin = 1 if self.points[p][week] >= self.points[oppo][week] else 0
        
                num_wins += isWin
            
            wins[p] = num_wins
        return wins
    

    def run_simulations(self, n_sims):
        # Intialize count of times each participant gets each rank
        ranks_count = {
            p: {i+1: 0 for i in range(self.n)} for p in self.participants
        }

        # Count of times each participant makes playoffs
        playoffs_count = {
            p: 0 for p in self.participants
        }

        for _ in range(n_sims):
            # Permute player id's - last team is fixed at n-1
            perm = self.sample_permutation()
            wins = self.simulate_schedule(perm)
            ranks = self.get_ranks_from_wins_points(wins, self.total_points)
            for p in self.participants:
                ranks_count[p][ranks[p]] += 1
                playoffs_count[p] += 1 if ranks[p] <= self.cutoff else 0

        return ranks_count, playoffs_count



if __name__== '__main__':
    total_sims = int(sys.argv[1])


    # Load weekly points and schedule data
    with open('points.json', 'r') as fp:
        points = json.load(fp)

    with open('schedule.json', 'r') as fp:
        schedule = json.load(fp)
    
    league = League(schedule, points)

    with open('actual_rankings.json', 'w') as fp:
        json.dump(league.ranks, fp)

    rc, pc = league.run_simulations(total_sims)


    with open('simulated_rankings.json', 'w') as fp:
        json.dump(rc, fp)

    with open('simulated_playoffs.json', 'w') as fp:
        json.dump({'counts': pc, 'total':total_sims}, fp)