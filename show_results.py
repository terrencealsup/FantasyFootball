import json
from matplotlib import pyplot as plt


plt.rcParams.update({
    "font.family": 'Arial Black',
    "font.size": 20,
    'axes.facecolor': '#999999'
})

import pandas as pd
import numpy as np

with open('rankings_new.json', 'r') as fp:
    ranks = json.load(fp)

with open('actual_rankings_new.json', 'r') as fp:
    actual_ranks = json.load(fp)



def get_median(rank_counts):
    nr = len(rank_counts.keys())  # Total number of possible ranks
    total = sum(rank_counts.values())
    
    cumsum = 0.0

    for r in range(nr, 0, -1):
        cumsum += rank_counts[str(r)]/total
        if cumsum >= 0.5:
            return r - (cumsum - 0.5)
    return total


participants = list(ranks.keys())
participants.sort(key=lambda x: -actual_ranks[x])
n = len(participants)

medians = {p: get_median(ranks[p]) for p in participants}

def get_percentile(p):
    r = actual_ranks[p]
    data = ranks[p]
    cumsum = 0.0
    total = 0.0
    for i, v in data.items():
        if int(i) > r:
            cumsum += v
        total += v
    return cumsum/total

percentiles = {p: get_percentile(p) for p in participants}



diff = {p: medians[p]-actual_ranks[p] for p in participants}
sorted_diff = sorted(diff, key=lambda x: -diff[x])
lucky_ranks = {s:diff[s] for s in sorted_diff}


# Print results to console
print('\n')
print(''.join(["="]*32))
r = 1
for p in lucky_ranks.keys():
    print(f"{r}, {p}, {lucky_ranks[p]}")
    r += 1
print('\n')



cmap = plt.get_cmap('RdYlGn', n)

pct_first = dict()
pct_last  = dict()

plt.rcParams.update({
    "font.family": 'Arial Black',
    "font.size": 20,
    'axes.facecolor': '#999999'
})

fig, ax = plt.subplots(figsize=(20, 40))
scale = 0.52
for i in range(n):
    y = scale*i
    data = ranks[participants[i]]
    data = np.array([[int(i), float(v)] for i, v in data.items()])
    data[:,1] = data[:,1] / data[:,1].sum()  # Normalize
    pct_first[participants[i]] = data[0,1]
    pct_last[participants[i]] = data[-1,1]

    
    ax.bar(x=data[:,0], height=data[:,1]/2, width=1, color=cmap(i), alpha=1.0, bottom=y, edgecolor='black')
    ax.bar(x=data[:,0], height=-data[:,1]/2, width=1, color=cmap(i), alpha=1.0, bottom=y, edgecolor='black')

    # Show actual
    if i == 0:
        ax.plot(actual_ranks[participants[i]], 
                y, 
                marker='x', 
                c='k', 
                markersize=20, 
                markeredgewidth=5, 
                label='Actual',
                ls=' '
               )
        ax.plot(medians[participants[i]], 
                y, 
                marker='o', 
                c='k', 
                markersize=20, 
                label='Median',
                ls=' '
               )
    else:
        ax.plot(actual_ranks[participants[i]], y, marker='x', c='k', markersize=20, markeredgewidth=5)
        ax.plot(medians[participants[i]], y, marker='o', c='k', markersize=20)    

ax.set_xticks(np.arange(n)+1)

tick_labels = [p + f'\n\nMedian place: {medians[p]:0.2f}\n\nFirst place: {100*pct_first[p]:0.2f}%\n\nLast place: {100*pct_last[p]:0.2f}%' for p in participants]
ax.set_yticks(scale*np.arange(n), tick_labels)

ax.legend()
ax.set_title("Player Standings")

plt.tight_layout()


fig.savefig('results_new.pdf')



