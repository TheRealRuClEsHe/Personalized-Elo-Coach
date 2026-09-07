# EloCoach

EloCoach analyses an Age of Empires II: Definitive Edition replay and returns
ranked coaching advice for one of the two players in it.

## Language

**Coached player**:
The player the analysis is about. Every feature and recommendation is oriented
from this player's point of view.
_Avoid_: me, my, user, uploader, subject

**Opponent**:
The other player in the replay. Exists only relative to the coached player.
_Avoid_: enemy, them, player 2

**Replay**:
An `.aoe2record` file recording a single game. The only input the analysis takes.
_Avoid_: save, game file, match file

**Delta feature**:
One measurement expressed as coached player minus opponent. Negative is better
for timings, positive is better for counts. The model is trained on these, never
on raw per-player values.
_Avoid_: feature, diff, differential
