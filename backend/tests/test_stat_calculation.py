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

    assert stats.hp == 265
    assert stats.phy_atk == 152
    assert stats.mag_atk == 113
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

    assert stats.hp == 214
    assert stats.phy_atk == 146
    assert stats.mag_atk == 113
    assert stats.phy_def == 161
    assert stats.mag_def == 143
    assert stats.spd == 282
    
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

    assert stats.hp == 285
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

    assert stats.hp == 234
    assert stats.phy_atk == 199
    assert stats.mag_atk == 256
    assert stats.phy_def == 166
    assert stats.mag_def == 188
    assert stats.spd == 238