# Section 6 — Feature Documentation Table (Updated v2)

**Updated:** 2026-05-19  
**Parser:** `mgz-fast` (mgz v1.8.51) via `parse_replay()`  
**Scope:** All fields extracted per player per game. One row per player per game in the flat CSV.

---

## Label & Grouping

| field_name | data_type | aoe2_meaning | expected_range | keep_for_model | notes |
|---|---|---|---|---|---|
| result | int | Did this player win? Training label. | 0 or 1 | **Required (label)** | 0=resigned, 1=other player resigned. None if no resign detected (edge case). |
| elo | int | Player's ranked 1v1 RM Elo at time of game | 800–2200 | **Required (grouping)** | From POSTGAME leaderboard id=3. Not in feature matrix X — used only for cohort assignment. Approximate: matchmaking swaps possible but not systematically biased. |

---

## Filter Columns (never enter model)

| field_name | data_type | aoe2_meaning | expected_range | keep_for_model | notes |
|---|---|---|---|---|---|
| filepath | str | Source .aoe2record file path | string | No | Debugging and dedup only. |
| map_id | int | Which map was played | 9 = Arabia | Filter only | Filter to 9 before modeling. |
| rated | bool | Was this a ranked game? | True/False | Filter only | Filter to True before modeling. |
| num_players | int | Total real players in game | 2 for 1v1 | Filter only | Filter to 2 before modeling. |
| resigned | bool | Did this player resign? | True/False | No | Used to derive result. Drop after derivation. |
| resign_time_min | float | When this player resigned | 0–90 min | No | Post-hoc — would leak result into features. |

---

## Game-Level Feature

| field_name | data_type | aoe2_meaning | expected_range | keep_for_model | notes |
|---|---|---|---|---|---|
| duration_min | float | How long the game lasted | 8–90 min | Yes | Games <8 min filtered in Week 2. Proxy for game style (aggression vs late game). |

---

## Age-Up Timings

| field_name | data_type | aoe2_meaning | expected_range | keep_for_model | notes |
|---|---|---|---|---|---|
| feudal_min | float | When player clicked up to Feudal Age | 8–30 min | Yes | Lower = faster = generally better. Core coaching signal. |
| castle_min | float | When player clicked up to Castle Age | 14–40 min | Yes | Measures mid-game transition speed. |
| imperial_min | float | When player clicked up to Imperial Age | 22–60 min | Maybe | ~50% null — many games end before Imperial. Impute with duration_min. |

---

## Eco Tech Timings

All nulls = player never researched this tech during the game. Impute with `duration_min` (encodes "researched at end or not at all").

| field_name | data_type | aoe2_meaning | expected_range | keep_for_model | notes |
|---|---|---|---|---|---|
| loom_min | float | Villager HP upgrade | 2–15 min | Yes | Early loom = defensive. Late loom = greedy eco opener. |
| double_bit_axe_min | float | +20% wood gather rate | 8–25 min | Yes | Core eco upgrade — almost universal. |
| bow_saw_min | float | +20% wood gather rate (tier 2) | 15–40 min | Yes | Mid-game eco. |
| two_man_saw_min | float | +20% wood gather rate (tier 3) | 25–60 min | Maybe | Late game, high null rate expected. |
| horse_collar_min | float | +15% food gather rate (farms) | 8–25 min | Yes | Early farm eco. Almost universal on Arabia. |
| heavy_plow_min | float | +15% food gather rate (farms, tier 2) | 14–40 min | Yes | Mid-game farm eco. |
| crop_rotation_min | float | +15% food gather rate (farms, tier 3) | 25–60 min | Maybe | High null — Imperial Age tech. |
| gold_mining_min | float | +15% gold gather rate | 10–30 min | Yes | Signals when player starts gold eco. |
| gold_shafting_mining_min | float | +15% gold gather rate (tier 2) | 20–45 min | Maybe | High null expected. |
| stone_mining_min | float | +15% stone gather rate | 15–40 min | Maybe | Less universal than gold/wood. |
| stone_shafting_mining_min | float | +15% stone gather rate (tier 2) | 25–60 min | Maybe | High null — drop if >50% null. |
| wheelbarrow_min | float | +25% villager carry capacity & speed | 12–30 min | Yes | Strong eco signal. Delay = inefficiency. |
| hand_cart_min | float | +50% carry capacity & speed (tier 2) | 25–50 min | Maybe | Often researched but mid-high null. |
| town_watch_min | float | Increases LoS of Town Center | 10–35 min | Maybe | Defensive awareness signal. |
| town_patrol_min | float | Increases LoS further (tier 2) | 25–55 min | Maybe | High null. |

---

## Military Tech Timings

Highly civ-dependent — a Cavalry civ will have barding, an Archer civ will have archer armor. Null = civ doesn't have the tech, OR player didn't research it. Consider dropping civ-specific techs or making them model features only within civ groups.

| field_name | data_type | aoe2_meaning | expected_range | keep_for_model | notes |
|---|---|---|---|---|---|
| fletching_min | float | +1 range attack for archers | 14–30 min | Yes | Very common. Early = archer-focused strategy. |
| bodkin_arrow_min | float | +1 range attack (tier 2) | 20–40 min | Yes | Common. |
| bracer_min | float | +1 range attack (tier 3) | 30–55 min | Maybe | Castle/Imperial age. |
| padded_archer_armor_min | float | Archer armor tier 1 | 14–30 min | Maybe | |
| leather_archer_armor_min | float | Archer armor tier 2 | 20–40 min | Maybe | |
| ring_archer_armor_min | float | Archer armor tier 3 | 30–55 min | Maybe | High null. |
| forging_min | float | +1 melee attack | 14–35 min | Yes | Signals melee/infantry focus. |
| iron_casting_min | float | +1 melee attack (tier 2) | 20–45 min | Maybe | |
| blast_furnace_min | float | +1 melee attack (tier 3) | 30–60 min | Maybe | High null. |
| scale_mail_armor_min | float | Infantry armor tier 1 | 14–35 min | Maybe | Infantry civs. |
| chain_mail_armor_min | float | Infantry armor tier 2 | 20–45 min | Maybe | |
| plate_mail_armor_min | float | Infantry armor tier 3 | 30–60 min | Maybe | High null. |
| scale_barding_armor_min | float | Cavalry armor tier 1 | 14–35 min | Maybe | Cavalry civs. |
| chain_barding_armor_min | float | Cavalry armor tier 2 | 20–45 min | Maybe | |
| plate_barding_armor_min | float | Cavalry armor tier 3 | 30–60 min | Maybe | High null. |
| bloodlines_min | float | +20 HP for cavalry | 14–35 min | Yes | Very common in cavalry civs. Strong coaching signal. |
| husbandry_min | float | +10% cavalry speed | 14–40 min | Yes | Common cavalry tech. |
| thumb_ring_min | float | Archers fire faster + full accuracy | 20–40 min | Yes | Strong archer signal. |
| parthian_tactics_min | float | Cav archer armor + attack bonus | 25–50 min | Maybe | Cav archer civs only. High null. |
| chemistry_min | float | +1 projectile attack for all units | 28–55 min | Maybe | Late game. Unlocks gunpowder. |
| arson_min | float | Infantry +2 attack vs buildings | 20–45 min | Maybe | Aggressive builds. |
| gambeson_min | float | Militia line +1 melee armor | 14–30 min | Maybe | Relatively new tech. |
| squires_min | float | Infantry move 10% faster | 15–35 min | Maybe | Infantry rush civs. |

---

## Building Timings (First Placement)

| field_name | data_type | aoe2_meaning | expected_range | keep_for_model | notes |
|---|---|---|---|---|---|
| first_barracks_min | float | When player placed first Barracks | 2–15 min | Yes | Very early barracks = flush/rush. Core build order signal. |
| first_stable_min | float | When player placed first Stable | 8–25 min | Yes | Signals cavalry strategy. |
| first_archery_min | float | When player placed first Archery Range | 8–25 min | Yes | Signals archer strategy. |
| market_min | float | When player placed first Market | 12–40 min | Maybe | Late eco signal. Coin trading strategy. |
| blacksmith_min | float | When player placed first Blacksmith | 14–35 min | Yes | Timing signals military upgrade commitment. |

---

## Phase-Binned Production Counts

Counts split by game phase (Dark/Feudal/Castle/Imperial Age). Phase boundaries derived from age-up tech timings + research duration offset.

| field_name | data_type | aoe2_meaning | expected_range | keep_for_model | notes |
|---|---|---|---|---|---|
| villagers_dark_age | int | Villagers trained before Feudal | 15–30 | Yes | Dark age eco build. <20 = eco deficit. |
| villagers_feudal_age | int | Villagers trained in Feudal Age | 5–25 | Yes | Eco vs military tradeoff in Feudal. |
| villagers_castle_age | int | Villagers trained in Castle Age | 10–60 | Yes | Eco commitment in mid-game. |
| villagers_imperial_age | int | Villagers trained in Imperial Age | 0–40 | Maybe | High null — many games don't reach Imp. |
| mil_trained_dark_age | int | Military units trained before Feudal | 0–5 | Maybe | Almost always 0 or scouts. Low signal. |
| mil_trained_feudal_age | int | Military units trained in Feudal Age | 0–30 | Yes | Aggression signal. High = aggressive Feudal play. |
| mil_trained_castle_age | int | Military units trained in Castle Age | 5–80 | Yes | Core military production metric. |
| mil_trained_imperial_age | int | Military units trained in Imperial Age | 0–100 | Maybe | High null. |
| apm_dark_age | int | Action commands issued before Feudal | 100–600 | Yes | Raw activity proxy. Low = idle player. |
| apm_feudal_age | int | Action commands issued in Feudal Age | 100–600 | Yes | Micro/macro intensity in Feudal. |
| apm_castle_age | int | Action commands issued in Castle Age | 200–1200 | Yes | Army management intensity mid-game. |
| apm_imperial_age | int | Action commands issued in Imperial Age | 100–800 | Maybe | High null. |

---

## Behavioral Action Counts (Game-Total)

| field_name | data_type | aoe2_meaning | expected_range | keep_for_model | notes |
|---|---|---|---|---|---|
| gather_point_count | int | Times player redirected TC/building gather points | 10–300 | Yes | Active eco management proxy. Low = idle villager problem. |
| wall_count | int | Wall segments placed | 0–200 | Yes | Defensive awareness. 0 at 1000–1200 Elo is common. |
| first_wall_min | float | When first wall segment was placed | 5–40 min | Yes | Early walling = proactive defense. Null = never walled. |
| move_count | int | MOVE commands issued | 100–3000 | Maybe | High noise. Correlated with APM. May be redundant. |
| order_count | int | ORDER commands issued | 50–1000 | Maybe | Army commands. Correlated with mil_trained. |
| stance_count | int | Unit stance changes | 10–300 | Yes | Army micro awareness. Low = army left on aggressive/passive. |
| ungarrison_count | int | Units ungarrisoned | 0–50 | Maybe | Low counts overall. Weak signal. |

---

## Internal / Drop Before Modeling

| field_name | data_type | notes |
|---|---|---|
| thresholds | dict | Internal phase boundary tracker. Flatten or drop. |
| military_buildings_placed | defaultdict(int) | Building volume tracker. Flatten keys to `barracks_count`, `stable_count`, etc. if wanted as features. |

---

## What Is NOT Available in .aoe2record

- Resources collected over time — engine-side, not in command log
- Villager gather rates — same
- Idle villager time — would require scanning all unit positions between commands; not feasible with mgz-fast
- Military unit idle time — same limitation
- Units lost in combat — deaths are engine-calculated, not logged as player commands
