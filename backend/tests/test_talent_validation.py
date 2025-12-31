import pytest
from backend.schemas import TalentIn

def test_talent_all_zero_forbidden():
    with pytest.raises(ValueError):
        TalentIn(
            hp_boost=0,
            phy_atk_boost=0,
            mag_atk_boost=0,
            phy_def_boost=0,
            mag_def_boost=0,
            spd_boost=0,
        )

def test_talent_too_many_boosts_forbidden():
    with pytest.raises(ValueError):
        TalentIn(
            hp_boost=10,
            phy_atk_boost=8,
            mag_atk_boost=10,
            phy_def_boost=9,
            mag_def_boost=0,
            spd_boost=0,
        )
        
def test_talent_invalid_value_forbidden():
    with pytest.raises(ValueError):
        TalentIn(
            hp_boost=10,
            phy_atk_boost=5,
            mag_atk_boost=0,
            phy_def_boost=0,
            mag_def_boost=0,
            spd_boost=0,
        )
        
def test_talent_minimal_valid():
    t = TalentIn(
        hp_boost=0,
        phy_atk_boost=0,
        mag_atk_boost=7,
        phy_def_boost=0,
        mag_def_boost=0,
        spd_boost=0,
    )
    assert t.mag_atk_boost == 7
    
def test_talent_two_boosts_valid():
    t = TalentIn(
        hp_boost=0,
        phy_atk_boost=8,
        mag_atk_boost=0,
        phy_def_boost=7,
        mag_def_boost=0,
        spd_boost=0,
    )
    assert t.phy_atk_boost == 8
    assert t.phy_def_boost == 7

def test_talent_three_boosts_valid():
    t = TalentIn(
        hp_boost=10,
        phy_atk_boost=0,
        mag_atk_boost=7,
        phy_def_boost=0,
        mag_def_boost=0,
        spd_boost=8,
    )
    assert t.hp_boost == 10
    assert t.mag_atk_boost == 7
    assert t.spd_boost == 8
    
def test_talent_all_three_same_boost_valid():
    t = TalentIn(
        hp_boost=9,
        phy_atk_boost=9,
        mag_atk_boost=9,
        phy_def_boost=0,
        mag_def_boost=0,
        spd_boost=0,
    )
    assert t.hp_boost == 9
    assert t.phy_atk_boost == 9
    assert t.mag_atk_boost == 9