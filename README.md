# FantasyFootball

Most Fantasy Football leagues follow a round robin format where each player plays every other player at some point according to some randomized schedule. This code can be used to quantify the luck in player's schedule relative to all other schedules the player could have had and ranks the player's accordingly.

## Getting started

The main file that runs the simulations for different schedules is `simulate.py`. To run this file you first need to fill out two JSON files: `schedule.json` and `points.json`. The format for `schedule.json` is as follows:

```
{
    "team 1": [
        "opponent 1",
        "opponent 2",
        ...
    ],
    ...
    "team n": [
        "opponent 1",
        "opponent 2",
        ...
    ]
}
```

Here each teams list of opponents is entered in sequentially starting from the first week to the last or most recent week. The lists must all have the same length.

The `points.json` file should list the number of points each team scores each week as so

```
{
    "team 1": [
        week 1 points,
        week 2 points,
        ...
    ],
    ...
    "team n" :[
        week 1 points,
        week 2 points,
        ...
    ]
}
```