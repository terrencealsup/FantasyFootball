import json
import sys
from itertools import permutations
import numpy as np
import argparse


# Parse optional arguments for number of simulations
parser = argparse.ArgumentParser(description = "simulate.py")
parser.add_argument("-N", "--nsims", help = "number of simulations to run (default is all permutations)", required = False, default = "")
argument = parser.parse_args()

if argument.nsims:
    n_sims = int(argument.nsims)
else:
    n_sims = None



# Load weekly points and schedule data
with open('points.json', 'r') as fp:
    points = json.load(fp)

with open('schedule.json', 'r') as fp:
    schedule = json.load(fp)



# Number of league participants and number of weeks
participants = list(points.keys())
n = len(participants)
n_weeks = max(len(points[p]) for p in participants)


# Total points scored used for tie-breaking
total_points = {p: sum(points[p]) for p in participants}

# Determine number of wins based on the actual schedule provided
wins = {}
for p in participants:
    num_wins = 0
    for week in range(n_weeks):
        # Get the opponent
        opp = schedule[p][week%(n-1)]

        isWin = 1 if points[p][week] >= points[opp][week] else 0

        num_wins += isWin 
    
    wins[p] = num_wins


def get_ranks_from_wins_points(wins, points, participants, n):
    """
    Derive the overall rank based on number of wins and points scored.

    @input:
        wins         - dict
        points       - dict
        participants - dict
        n            - int
    @return:
        ranks - dict
    """

    df = np.rec.fromrecords(
        [(p, wins[p], points[p]) for p in participants], 
        dtype=[("participant", "U32"), ("wins", int), ("points", float)]
    )
    ix = np.argsort(df, order=['wins', 'points'])
    ranks = {participants[ix[i]]: n-i for i in range(n)}
    return ranks

# Get actual rankings from provided schedule
ranks = get_ranks_from_wins_points(wins, total_points, participants, n)




def simulate_schedule(ids, p_id, n, n_weeks, points):
    """
    Run a simulation 
    """

    wins = {}
    for i in ids:
        team = p_id[i]
        num_wins = 0
        for week in range(n_weeks):
            # Get the opponent
            oppo = p_id[(week - i) % n]
    
            isWin = 1 if points[team][week] >= points[oppo][week] else 0
    
            num_wins += isWin 
        
        wins[team] = num_wins
    
    return wins




# Intialize count of times each participant gets each rank
ranks_count = {
    p: {i+1: 0 for i in range(n)} for p in participants
}


if not n_sims:
    j = 0
    for x in permutations(range(n-1)):
        # Permute player id's - last team is fixed at n-1
        #ids = np.append(np.random.permutation(range(n-1)), n-1)
        ids = list(x)
        ids.append(n-1)
        p_id = [participants[p] for p in ids]  # p_ids[i] gives the participant with id=i
        wins = simulate_schedule(ids, p_id, n, n_weeks, points)
        ranks = get_ranks_from_wins_points(wins, total_points, participants, n)
        for r in ranks.keys():
            ranks_count[r][ranks[r]] += 1

        if j%1_000_000 == 0:
            print(j//1_000_000)
        j += 1
else:
    for j in range(n_sims):
        # Permute player id's - last team is fixed at n-1
        ids = np.append(np.random.permutation(range(n-1)), n-1)
        p_id = [participants[p] for p in ids]  # p_ids[i] gives the participant with id=i
        wins = simulate_schedule(ids, p_id, n, n_weeks, points)
        ranks = get_ranks_from_wins_points(wins, total_points, participants, n)
        for r in ranks.keys():
            ranks_count[r][ranks[r]] += 1


with open('temp.json', 'w') as fp:
    json.dump(ranks_count, fp)
