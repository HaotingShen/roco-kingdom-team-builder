import pytest
from backend.main import compute_effective_stats

class Dummy:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

def test_effective_stats_flutterfly_cheerful_max_boosts():
    # Dummy test data to mimic real model's attribute names
    monster = Dummy(
        base_hp=55,
        base_phy_atk=54,
        base_mag_atk=55,
        base_phy_def=71,
        base_mag_def=75,
        base_spd=140,
    )
    talent = Dummy(
        hp_boost=10,
        phy_atk_boost=10,
        mag_atk_boost=0,
        phy_def_boost=0,
        mag_def_boost=0,
        spd_boost=10,
    )
    personality = Dummy(
        hp_mod_pct=0,
        phy_atk_mod_pct=0,
        mag_atk_mod_pct=-0.1,
        phy_def_mod_pct=0,
        mag_def_mod_pct=0,
        spd_mod_pct=0.2,
    )
    stats = compute_effective_stats(monster, personality, talent)

    # Formula: round(round((2·base + 6·talent)·0.85 + 70) · (1+mod) + 100)  for hp
    #          round(round((2·base + 6·talent)·0.55 + 10) · (1+mod) + 50)   for others
    # hp:       170·0.85 + 70 = 214.5 → round=215 → 215·1 + 100 = 315
    # phy_atk:  168·0.55 + 10 = 102.4 → round=102 → 102·1 + 50  = 152
    # mag_atk:  110·0.55 + 10 = 70.5  → round=71  → 71·0.9 + 50 = 113.9 → 114
    # phy_def:  142·0.55 + 10 = 88.1  → round=88  → 88·1 + 50   = 138
    # mag_def:  150·0.55 + 10 = 92.5  → round=93  → 93·1 + 50   = 143
    # spd:      340·0.55 + 10 = 197   → round=197 → 197·1.2 + 50 = 286.4 → 286
    assert stats.hp == 315
    assert stats.phy_atk == 152
    assert stats.mag_atk == 114
    assert stats.phy_def == 138
    assert stats.mag_def == 143
    assert stats.spd == 286

def test_effective_stats_flutterfly_cheerful_random_boosts():
    monster = Dummy(
        base_hp=55,
        base_phy_atk=54,
        base_mag_atk=55,
        base_phy_def=71,
        base_mag_def=75,
        base_spd=140,
    )
    talent = Dummy(
        hp_boost=0,
        phy_atk_boost=8,
        mag_atk_boost=0,
        phy_def_boost=7,
        mag_def_boost=0,
        spd_boost=9,
    )
    personality = Dummy(
        hp_mod_pct=0,
        phy_atk_mod_pct=0,
        mag_atk_mod_pct=-0.1,
        phy_def_mod_pct=0,
        mag_def_mod_pct=0,
        spd_mod_pct=0.2,
    )
    stats = compute_effective_stats(monster, personality, talent)

    # hp:       110·0.85 + 70 = 163.5 → round=164 → 164·1 + 100 = 264
    # phy_atk:  156·0.55 + 10 = 95.8  → round=96  → 96·1 + 50   = 146
    # mag_atk:  110·0.55 + 10 = 70.5  → round=71  → 71·0.9 + 50 = 113.9 → 114
    # phy_def:  184·0.55 + 10 = 111.2 → round=111 → 111·1 + 50  = 161
    # mag_def:  150·0.55 + 10 = 92.5  → round=93  → 93·1 + 50   = 143
    # spd:      334·0.55 + 10 = 193.7 → round=194 → 194·1.2 + 50 = 282.8 → 283
    assert stats.hp == 264
    assert stats.phy_atk == 146
    assert stats.mag_atk == 114
    assert stats.phy_def == 161
    assert stats.mag_def == 143
    assert stats.spd == 283

def test_effective_stats_starlion_timid_max_boosts():
    monster = Dummy(
        base_hp=67,
        base_phy_atk=117,
        base_mag_atk=117,
        base_phy_def=96,
        base_mag_def=116,
        base_spd=135,
    )
    talent = Dummy(
        hp_boost=10,
        phy_atk_boost=0,
        mag_atk_boost=10,
        phy_def_boost=0,
        mag_def_boost=0,
        spd_boost=10,
    )
    personality = Dummy(
        hp_mod_pct=0,
        phy_atk_mod_pct=-0.1,
        mag_atk_mod_pct=0,
        phy_def_mod_pct=0,
        mag_def_mod_pct=0,
        spd_mod_pct=0.2,
    )
    stats = compute_effective_stats(monster, personality, talent)

    # hp:       194·0.85 + 70 = 234.9 → round=235 → 235·1 + 100 = 335
    # phy_atk:  234·0.55 + 10 = 138.7 → round=139 → 139·0.9 + 50 = 175.1 → 175
    # mag_atk:  294·0.55 + 10 = 171.7 → round=172 → 172·1 + 50   = 222
    # phy_def:  192·0.55 + 10 = 115.6 → round=116 → 116·1 + 50   = 166
    # mag_def:  232·0.55 + 10 = 137.6 → round=138 → 138·1 + 50   = 188
    # spd:      330·0.55 + 10 = 191.5 → round=192 → 192·1.2 + 50 = 280.4 → 280
    assert stats.hp == 335
    assert stats.phy_atk == 175
    assert stats.mag_atk == 222
    assert stats.phy_def == 166
    assert stats.mag_def == 188
    assert stats.spd == 280

def test_effective_stats_starlion_modest_random_boosts():
    monster = Dummy(
        base_hp=67,
        base_phy_atk=117,
        base_mag_atk=117,
        base_phy_def=96,
        base_mag_def=116,
        base_spd=135,
    )
    talent = Dummy(
        hp_boost=0,
        phy_atk_boost=8,
        mag_atk_boost=10,
        phy_def_boost=0,
        mag_def_boost=0,
        spd_boost=9,
    )
    personality = Dummy(
        hp_mod_pct=0,
        phy_atk_mod_pct=-0.1,
        mag_atk_mod_pct=0.2,
        phy_def_mod_pct=0,
        mag_def_mod_pct=0,
        spd_mod_pct=0,
    )
    stats = compute_effective_stats(monster, personality, talent)

    # hp:       134·0.85 + 70 = 183.9 → round=184 → 184·1 + 100 = 284
    # phy_atk:  282·0.55 + 10 = 165.1 → round=165 → 165·0.9 + 50 = 198.5 → 199
    # mag_atk:  294·0.55 + 10 = 171.7 → round=172 → 172·1.2 + 50 = 256.4 → 256
    # phy_def:  192·0.55 + 10 = 115.6 → round=116 → 116·1 + 50   = 166
    # mag_def:  232·0.55 + 10 = 137.6 → round=138 → 138·1 + 50   = 188
    # spd:      324·0.55 + 10 = 188.2 → round=188 → 188·1 + 50   = 238
    assert stats.hp == 284
    assert stats.phy_atk == 199
    assert stats.mag_atk == 256
    assert stats.phy_def == 166
    assert stats.mag_def == 188
    assert stats.spd == 238