# Quick Start Guide - Data Validation

## TL;DR

```bash
# Activate virtual environment
source ~/.venvs/rktb310/bin/activate

# Run all validation checks at once
python3 backend/scripts/validation/run_all_checks.py

# Or run individually
python3 backend/scripts/validation/check_frontend_images.py
python3 backend/scripts/validation/check_local_consistency.py
python3 backend/scripts/validation/check_source_correctness.py
```

## What Each Script Does

### 🔍 check_local_consistency.py
Validates `monsters.json` against other local JSON files (types, traits, species, monster_moves).

**Checks:**
- Missing or misspelled species, types, traits
- Evolution chain consistency
- Form naming conventions
- Leader flags correctness
- Base stats and preferred attack style
- Moveset key existence and naming rules

### 📊 check_source_correctness.py
Compares local JSON files with `data_all.xlsx` (single source of truth).

**Checks:**
- Monster coverage (missing/extra monsters)
- Base stats accuracy
- Type assignments
- Trait assignments
- Moveset completeness

### 🖼️ check_frontend_images.py
Validates frontend image files (monster images, move icons, magic item images).

**Checks:**
- All monsters have images in 180/270/360 folders
- All moves have icon images
- All magic items have images
- Identifies orphaned images

### 🚀 run_all_checks.py
Runs all three validation scripts in sequence and generates a comprehensive combined report.

**Includes:**
- Frontend Images Check
- Local Consistency Check
- Source Correctness Check

**Output:**
- Terminal: Color-coded results from all checks with full details (no truncation)
- File: Single `combined_validation_report_YYYYMMDD_HHMMSS.txt` with complete results from all three checks

**Note:** Only one combined report file is generated - individual check reports are not saved separately.

## Reading the Output

### ✓ Green Checkmark
Section passed validation

### ✗ Red Cross (Error)
Critical issue that must be fixed

### ⚠ Yellow Warning
Potential issue to review (may be intentional)

### ℹ Blue Info
Informational message (unused definitions, etc.)

## Exit Codes

- `0` = Passed (may have warnings)
- `1` = Failed (has errors)

## Common Fixes

### Missing Trait
Add the trait to `backend/data/traits.json`

### Stat Mismatch
Update the JSON file to match Excel values or vice versa

### Missing Moveset Key
Add the moveset to `backend/data/monster_moves.json`

### Incorrect Preferred Attack Style
Check the base_phy_atk vs base_mag_atk values

## Tips

**Limit Output:**
```bash
python3 backend/scripts/validation/check_local_consistency.py | head -200
```

**Save to File:**
```bash
python3 backend/scripts/validation/run_all_checks.py > validation_report.txt 2>&1
```

**Focus on Errors Only:**
```bash
python3 backend/scripts/validation/check_local_consistency.py | grep "✗"
```

## More Info

See [README.md](README.md) for detailed documentation.
