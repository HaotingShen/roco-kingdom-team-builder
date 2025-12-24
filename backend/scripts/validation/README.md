# Data Validation Scripts

This folder contains comprehensive data validation scripts for the Roco Kingdom Team Builder project.

## Overview

Three main validation scripts ensure data quality and consistency:

1. **`check_frontend_images.py`** - Validates frontend image files exist and match data
2. **`check_local_consistency.py`** - Validates local JSON files against each other
3. **`check_source_correctness.py`** - Validates local JSON files against the source Excel file

**Quick Run:** Use `run_all_checks.py` to run all three checks at once and generate a single combined report.

## Scripts

### 0. Run All Checks (Recommended)

**File:** `run_all_checks.py`

**Purpose:** Orchestrates all three validation scripts and generates a single comprehensive report.

**Usage:**
```bash
# From project root
source ~/.venvs/rktb310/bin/activate
python3 backend/scripts/validation/run_all_checks.py
```

**Output:**
- Terminal: Color-coded summary from all three checks
- File: `combined_validation_report_YYYYMMDD_HHMMSS.txt` - Single comprehensive report with all validation results

---

### 1. Frontend Images Validation

**File:** `check_frontend_images.py`

**Purpose:** Validates that all frontend image files exist and match the data definitions.

**What it checks:**

#### Monster Images
- All monsters have images in three sizes: 180px, 270px, 360px
- Image filenames match Chinese names from `monsters.json`
- Identifies orphaned images (files not referenced in data)
- Detects shiny variant images (异色)

#### Move Icons
- All moves have corresponding icon images
- Icon filenames match Chinese move names
- Identifies orphaned icons

#### Magic Item Images
- All magic items have corresponding images
- Image filenames match item names

**Usage:**
```bash
# From project root
source ~/.venvs/rktb310/bin/activate
python3 backend/scripts/validation/check_frontend_images.py
```

**Output:**
- Summary statistics (counts of images found/missing)
- Detailed list of missing images with expected filenames
- List of orphaned images (exist in folders but not in data)

---

### 2. Local Data Consistency Checker

**File:** `check_local_consistency.py`

**Purpose:** Validates the internal consistency of `monsters.json` and checks cross-references with other local JSON files.

**What it checks:**

#### Monster Species (`monster_species.json`)
- All species referenced in `monsters.json` exist in `monster_species.json`
- Identifies unused species definitions

#### Types (`types.json`)
- All `main_type` and `sub_type` values exist in `types.json`
- Type names are valid

#### Traits (`traits.json`)
- All trait names used in `monsters.json` exist in `traits.json`
- Identifies unused trait definitions

#### Monster Data Validation
For each monster entry in `monsters.json`:
- **Localization:** Chinese name exists in `localized.zh.name`
- **Evolution Chain:** `evolves_from` references valid monster names
- **Species:** Species name matches an entry in `monster_species.json` and represents the base evolution stage
- **Form:**
  - If no Chinese form name exists, `form` should be "default"
  - If Chinese form name exists, `form` should not be "default"
- **Types:**
  - `main_type` exists in `types.json`
  - `sub_type` exists in `types.json` (if not null)
  - `sub_type` is different from `main_type`
- **Legacy Type:**
  - If `is_leader_form` is `true`, `default_legacy_type` should be "Leader"
  - If `is_leader_form` is `false`, `default_legacy_type` should equal `main_type`
- **Leader Flags:**
  - `leader_potential` is `true` only if the next monster in the same species is a Leader
  - `is_leader_form` matches whether the monster has a different trait from its pre-evolution
- **Base Stats:**
  - All six base stats are present and valid (non-negative numbers)
- **Preferred Attack Style:**
  - "Physical" if `base_phy_atk` > `base_mag_atk`
  - "Magic" if `base_mag_atk` > `base_phy_atk`
  - "Both" if they are equal

#### Moveset Keys (`monster_moves.json`)
- Each `moveset_key` exists in `monster_moves.json`
- Moveset key follows naming conventions:
  - Format: `<highest_evo_zh_name>-<form_zh_name>` (if form exists)
  - Format: `<highest_evo_zh_name>` (if no form)
  - For branching evolutions, each branch has its own moveset key

**Usage:**
```bash
# From project root
source ~/.venvs/rktb310/bin/activate
python3 backend/scripts/validation/check_local_consistency.py
```

**Output:**
- ✓ Green checkmarks for successful checks
- ✗ Red errors for critical issues that must be fixed
- ⚠ Yellow warnings for potential issues to review
- ℹ Blue info messages for informational notices

---

### 3. Source Data Correctness Checker

**File:** `check_source_correctness.py`

**Purpose:** Validates local JSON files against the single source of truth: `data_all.xlsx`

**Requirements:**
```bash
pip install openpyxl
```

**What it checks:**

#### Monster Data Coverage
- All monsters in Excel exist in `monsters.json`
- Identifies extra monsters in JSON not present in Excel

#### Base Stats Validation
Compares all six base stats for each monster:
- `base_hp`
- `base_phy_atk`
- `base_mag_atk`
- `base_phy_def`
- `base_mag_def`
- `base_spd`

#### Type Validation
- `main_type` matches between Excel (Chinese) and JSON (English)
- `sub_type` matches between Excel and JSON

#### Trait Validation
- Trait names match between Excel (Chinese) and JSON (English)

#### Moveset Coverage
- All movesets in Excel exist in `monster_moves.json`
- Identifies extra movesets in JSON

#### Moveset Contents
For each moveset, compares three categories:
- **Learnable moves** (`自学技能`)
- **Move stones** (`技能石`)
- **Legacy moves** (`血脉技能`)

**Usage:**
```bash
# From project root
source ~/.venvs/rktb310/bin/activate
python3 backend/scripts/validation/check_source_correctness.py
```

**Output:**
- Detailed comparison between Excel source and JSON files
- Error count and mismatch details
- Coverage statistics

---

## Excel File Structure

### Sheet 1: 基础属性 (Monster Attributes)

| Column | Name | Description |
|--------|------|-------------|
| 1 | 编号 | Monster ID |
| 2 | 精灵名称 | Monster Name (Chinese) |
| 3 | 阶段 | Evolution Stage |
| 4 | 进化条件 | Evolution Condition |
| 5 | 属性 | Type(s) |
| 7 | 特性 | Trait (name: description format) |
| 8-13 | Base Stats | HP, Phy Atk, Mag Atk, Phy Def, Mag Def, Speed |

### Sheet 2: 技能表 (Move Table)

| Columns | Name | Description |
|---------|------|-------------|
| 1 | 编号 | Monster ID |
| 2 | 精灵名称 | Monster Name (Chinese) |
| 3-40 | 自学技能 | Learnable Moves |
| 41-61 | 技能石 | Move Stones |
| 62-79 | 血脉技能 | Legacy Moves |

---

## Common Issues Found

### Local Consistency Issues

1. **Missing Traits:**
   - Trait names in `monsters.json` that don't exist in `traits.json`
   - Example: "Skybreak"

2. **Incorrect Preferred Attack Style:**
   - Mismatches between calculated value based on stats and stored value
   - Example: Monster has equal physical and magic attack but is marked "Physical"

3. **Missing Moveset Keys:**
   - `moveset_key` in `monsters.json` that doesn't exist in `monster_moves.json`
   - Example: "月亮砣-上弦的样子"

4. **Moveset Key Naming Violations:**
   - Keys that don't follow the standard naming convention
   - Usually occurs with branching evolutions or special forms

### Source Correctness Issues

1. **Missing Monsters:**
   - Monsters in Excel but not in JSON
   - Common with form variants (e.g., "丢丢-沙地附近的样子")

2. **Stat Mismatches:**
   - Base stats differ between Excel and JSON
   - May indicate outdated data or manual errors

3. **Type Mismatches:**
   - Type assignments don't match between source and JSON
   - Translation errors or data import issues

4. **Moveset Differences:**
   - Move lists differ between Excel and JSON
   - May indicate game updates or data entry errors

---

## Interpreting Results

### Exit Codes
- `0` - Validation passed (may have warnings)
- `1` - Validation failed (has errors)

### Error Levels

**Errors (Red ✗):**
- Critical issues that should be fixed
- Data integrity problems
- Missing required data

**Warnings (Yellow ⚠):**
- Potential issues to review
- Naming convention violations
- Data that exists in one source but not another

**Info (Blue ℹ):**
- Informational messages
- Unused definitions
- Extra data that may be intentional

---

## Workflow Recommendations

### Regular Validation
Run both scripts regularly during development:
```bash
# Check local consistency first
python3 backend/scripts/validation/check_local_consistency.py

# Then check against source
python3 backend/scripts/validation/check_source_correctness.py
```

### After Data Updates
1. Update `data_all.xlsx` with new game data
2. Run source correctness checker to identify differences
3. Update local JSON files as needed
4. Run local consistency checker to ensure internal consistency
5. Fix any errors before committing

### Before Releases
- Both scripts must pass with 0 errors
- Review and document any warnings
- Ensure data integrity before deployment

---

## Extending the Scripts

### Adding New Checks

Both scripts are structured with modular check methods:

```python
def check_something_new(self):
    """Check for new validation rule."""
    print(f"{Colors.BOLD}Checking new validation...{Colors.RESET}")

    # Your validation logic here

    if error_condition:
        self.error(f"Error message")
    elif warning_condition:
        self.warning(f"Warning message")

    print(f"  ✓ Check complete\n")
```

Add new check methods to the `check_all()` method to include them in the validation run.

### Customizing Output

Modify the `print_summary()` method to:
- Change output format
- Export results to JSON or CSV
- Generate HTML reports
- Send notifications

---

## Troubleshooting

### "openpyxl not found" Error
```bash
source ~/.venvs/rktb310/bin/activate
pip install openpyxl
```

### "File not found" Errors
- Ensure you're running from the project root directory
- Verify `backend/data/` contains all required JSON files
- Check that `backend/data/data_all.xlsx` exists

### Too Many Errors
- Start with local consistency checker to fix internal issues
- Use `head` to limit output: `python3 script.py | head -200`
- Focus on error categories one at a time

---

## Future Improvements

Potential enhancements:

1. **JSON Schema Validation:**
   - Define JSON schemas for all data files
   - Validate structure before content

2. **Automated Fixes:**
   - Auto-correct common issues
   - Generate fix suggestions

3. **Diff Reports:**
   - Generate detailed diff reports
   - Track changes over time

4. **CI/CD Integration:**
   - Run validation on every commit
   - Block merges with validation errors

5. **Performance Optimization:**
   - Parallel validation checks
   - Caching for large datasets

6. **Web Interface:**
   - Visual validation dashboard
   - Interactive error review

---

## Contact

For issues or questions about these validation scripts, please refer to the main project documentation or contact the development team.
