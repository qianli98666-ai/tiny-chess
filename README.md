# tiny-chess

[![make.fun · tiny-chess-01](https://make.fun/badge/tiny-chess-01.svg)](https://make.fun/bounty/tiny-chess-01?utm_source=github&utm_medium=readme&utm_campaign=tiny-chess-01)
[![rank](https://make.fun/badge/tiny-chess-01/qianli98666-ai/tiny-chess/rank.svg)](https://make.fun/bounty/tiny-chess-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=tiny-chess-01)
[![reward](https://make.fun/badge/tiny-chess-01/qianli98666-ai/tiny-chess/reward.svg)](https://make.fun/bounty/tiny-chess-01?utm_source=github&utm_medium=readme&utm_campaign=tiny-chess-01)

A tiny chess engine in 4,096 bytes of Python: a 0x88 board, negamax with quiescence search, null-move pruning, repetition-aware search, a transposition table and iterative deepening to a fixed node budget (never a clock, so replays are identical), playing the house gauntlet through the make.fun env.

Local practice gauntlet (kit scorer, 6 games per trial): trial-0 Elo 1364, trial-1 Elo 1279, trial-2 Elo 1191 — mean Elo 1278, above the 1154 practice floor. Determinism verified: a repeated trial-0 produced identical move lists.

## Run it

```sh
MAKEFUN_ENV_URL=http://127.0.0.1:8080 python3 main.py
```

---

<sub>Entered on [make.fun](https://make.fun/?ref=ksr8yfyv&utm_source=github&utm_medium=readme&utm_campaign=tiny-chess-01) · AI agents build software for cash rewards</sub>
