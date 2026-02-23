import os
import pytest
from sqlalchemy.orm import Session
from backend.models import Type, Base
from backend.config import DATABASE_URL
from sqlalchemy import create_engine

pytestmark = pytest.mark.skipif(
    os.environ.get("ENVIRONMENT") == "testing",
    reason="Requires seeded game data in PostgreSQL — run manually after data import"
)

TYPE_EXPECTATIONS = {
    "Fire": {
        "effective_against": ["Grass", "Ice", "Bug", "Mechanical"],
        "weak_against": ["Water", "Ground", "Dragon"],
        "vulnerable_to": ["Water", "Ground"],
        "resistant_to": ["Grass", "Ice", "Cute", "Bug", "Mechanical"]
    },
    "Water": {
        "effective_against": ["Fire", "Ground", "Mechanical"],
        "weak_against": ["Grass", "Ice", "Dragon"],
        "vulnerable_to": ["Grass", "Electric"],
        "resistant_to": ["Fire", "Mechanical"]
    },
    "Grass": {
        "effective_against": ["Water", "Ground", "Light"],
        "weak_against": ["Fire", "Dragon", "Poison", "Bug", "Flying", "Mechanical"],
        "vulnerable_to": ["Fire", "Ice", "Poison", "Bug", "Flying"],
        "resistant_to": ["Water", "Light", "Ground", "Electric"]
    },
    "Dragon": {
        "effective_against": ["Dragon"],
        "weak_against": ["Mechanical"],
        "vulnerable_to": ["Ice", "Dragon", "Cute"],
        "resistant_to": ["Grass", "Fire", "Water", "Electric", "Flying"]
    },
    "Mechanical": {
        "effective_against": ["Ground", "Ice", "Cute"],
        "weak_against": ["Fire", "Water", "Electric", "Mechanical"],
        "vulnerable_to": ["Fire", "Water", "Fighting"],
        "resistant_to": ["Normal", "Poison", "Ice", "Flying", "Bug", "Cute", "Grass", "Mechanical", "Dragon", "Illusion"]
    },
    "Illusion": {
        "effective_against": ["Poison", "Fighting"],
        "weak_against": ["Light", "Illusion", "Mechanical"],
        "vulnerable_to": ["Ghost", "Bug"],
        "resistant_to": ["Fighting", "Illusion"]
    },
    "Normal": {
        "effective_against": [],
        "weak_against": ["Ground", "Ghost", "Mechanical"],
        "vulnerable_to": ["Fighting"],
        "resistant_to": ["Ghost"]
    },
    "Cute": {
        "effective_against": ["Dragon", "Fighting", "Dark"],
        "weak_against": ["Fire", "Poison", "Mechanical"],
        "vulnerable_to": ["Dark", "Poison", "Mechanical"],
        "resistant_to": ["Bug", "Fighting"]
    },
    "Dark": {
        "effective_against": ["Poison", "Ghost", "Cute"],
        "weak_against": ["Light", "Fighting", "Dark"],
        "vulnerable_to": ["Light", "Fighting", "Bug", "Cute"],
        "resistant_to": ["Ghost", "Dark"]
    },
    "Ghost": {
        "effective_against": ["Light", "Ghost", "Illusion"],
        "weak_against": ["Normal", "Dark"],
        "vulnerable_to": ["Light", "Ghost", "Dark"],
        "resistant_to": ["Normal", "Poison", "Bug", "Fighting"]
    },
    "Flying": {
        "effective_against": ["Grass", "Bug", "Fighting"],
        "weak_against": ["Ground", "Dragon", "Electric", "Mechanical"],
        "vulnerable_to": ["Electric", "Ice"],
        "resistant_to": ["Grass", "Bug", "Fighting"]
    },
    "Fighting": {
        "effective_against": ["Normal", "Ground", "Ice", "Dark", "Mechanical"],
        "weak_against": ["Poison", "Bug", "Flying", "Cute", "Ghost", "Illusion"],
        "vulnerable_to": ["Cute", "Flying", "Illusion"],
        "resistant_to": ["Ground", "Bug", "Dark"]
    },
    "Bug": {
        "effective_against": ["Grass", "Illusion", "Dark"],
        "weak_against": ["Fire", "Poison", "Fighting", "Flying", "Cute", "Ghost", "Mechanical"],
        "vulnerable_to": ["Flying", "Fire"],
        "resistant_to": ["Grass", "Fighting"]
    },
    "Poison": {
        "effective_against": ["Grass", "Cute"],
        "weak_against": ["Ground", "Poison", "Ghost", "Mechanical"],
        "vulnerable_to": ["Ground", "Illusion", "Dark"],
        "resistant_to": ["Grass", "Poison", "Bug", "Fighting", "Cute"]
    },
    "Electric": {
        "effective_against": ["Water", "Flying"],
        "weak_against": ["Grass", "Ground", "Dragon", "Electric"],
        "vulnerable_to": ["Ground"],
        "resistant_to": ["Electric", "Flying", "Mechanical"]
    },
    "Ice": {
        "effective_against": ["Grass", "Ground", "Dragon", "Flying"],
        "weak_against": ["Fire", "Ice", "Mechanical"],
        "vulnerable_to": ["Fire", "Ground", "Fighting", "Mechanical"],
        "resistant_to": ["Water", "Light", "Ice"]
    },
    "Ground": {
        "effective_against": ["Fire", "Ice", "Electric", "Poison"],
        "weak_against": ["Grass", "Fighting"],
        "vulnerable_to": ["Grass", "Water", "Ice", "Fighting", "Mechanical"],
        "resistant_to": ["Normal", "Fire", "Electric", "Poison", "Flying"]
    },
    "Light": {
        "effective_against": ["Ghost", "Dark"],
        "weak_against": ["Grass", "Ice"],
        "vulnerable_to": ["Ghost", "Grass"],
        "resistant_to": ["Illusion", "Dark"]
    }
}

@pytest.fixture(scope="module")
def session():
    engine = create_engine(DATABASE_URL)
    with Session(engine) as session:
        yield session

@pytest.mark.parametrize("type_name, expectations", TYPE_EXPECTATIONS.items())
def test_type_relationships(session, type_name, expectations):
    typ = session.query(Type).filter_by(name=type_name).first()
    assert typ is not None, f"Type {type_name} not found in DB"

    # Get relationship names as sets for easy comparison (order doesn't matter)
    eff_actual = {t.name for t in typ.effective_against}
    weak_actual = {t.name for t in typ.weak_against}
    vuln_actual = {t.name for t in typ.vulnerable_to}
    resist_actual = {t.name for t in typ.resistant_to}

    # Compare with expected sets
    assert eff_actual == set(expectations["effective_against"]), \
        f"{type_name}: effective_against mismatch (expected {expectations['effective_against']}, got {list(eff_actual)})"
    assert weak_actual == set(expectations["weak_against"]), \
        f"{type_name}: weak_against mismatch (expected {expectations['weak_against']}, got {list(weak_actual)})"
    assert vuln_actual == set(expectations["vulnerable_to"]), \
        f"{type_name}: vulnerable_to mismatch (expected {expectations['vulnerable_to']}, got {list(vuln_actual)})"
    assert resist_actual == set(expectations["resistant_to"]), \
        f"{type_name}: resistant_to mismatch (expected {expectations['resistant_to']}, got {list(resist_actual)})"