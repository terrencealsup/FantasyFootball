import json
import numpy as np
import pandas as pd
from matplotlib import pyplot as plt


with open('simulated_rankings.json', 'r') as fp:
    ranks = json.load(fp)

with open('actual_rankings.json', 'r') as fp:
    actual_ranks = json.load(fp)

with open('simulated_playoffs.json', 'r') as fp:
    playoffs = json.load(fp)

with open('points.json', 'r') as fp:
    points = json.load(fp)



# Get the most likely final ranking for each player
modal_ranking = dict()
for p in ranks.keys():
    modal_ranking[p] = int(max(ranks[p], key=ranks[p].get))


# Get percentage in first and last place finishes
pct_first = dict()
pct_last = dict()
for p in ranks.keys():
    total = sum(ranks[p].values())
    pct_first[p] = ranks[p]['1']
    pct_last[p] = ranks[p]['12']


data = []
for p in actual_ranks.keys():
    row = {
        'Team': p,
        'Actual': actual_ranks[p],
        'Most Likely': modal_ranking[p],
        'Playoffs Made': playoffs['counts'][p]/playoffs['total'],
        'Total Points For': sum(points[p]),
        'First': pct_first[p],
        'Last': pct_last[p]
    }
    data.append(row)

df = pd.DataFrame.from_records(data)
df.sort_values(by='Actual', ascending=True, inplace=True, ignore_index=True)

print(df)
