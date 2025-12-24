# Monster Type Fixer

A script to automatically correct monster typing errors in `monsters.json` using Excel as the source of truth.

## What It Does

The script:
1. **Reads** monster types from Excel (columns 5-6: 主属性/副属性)
2. **Matches** monsters between Excel and JSON by Chinese name + form
3. **Detects** type mismatches (main_type, sub_type, and default_legacy_type)
4. **Fixes** incorrect types in monsters.json following these rules:
   - `main_type` and `sub_type` → match Excel data
   - `default_legacy_type` → "Leader" for leader monsters, otherwise matches `main_type`
5. **Creates** automatic backups before making changes
6. **Logs** all changes for review

## Usage

### Run the Script

```bash
# Activate virtual environment
source ~/.venvs/rktb310/bin/activate

# Run from project root
python3 -m backend.scripts.maintenance.fix_monster_types
```

### What to Expect

The script will:
1. Load Excel and JSON data
2. Show all detected type mismatches with before/after values
3. Ask for confirmation before applying changes
4. Create a backup file: `monsters.json.backup_YYYYMMDD_HHMMSS`
5. Update `monsters.json` with corrected types
6. Generate a change log: `type_fixes_log_YYYYMMDD_HHMMSS.json`

### Example Output

```
================================================================================
Monster Type Fixer
================================================================================

Loading Excel data...
  Loaded 454 monsters from Excel

Loading JSON data...
  Loaded 503 monsters from JSON

Checking and fixing type mismatches...

Fixing Hornspike (尖角蜘蛛):
  main_type: Poison → Bug
  sub_type: Bug → Poison

Fixing Yamhorntitan (芋香巨角蛛):
  main_type: Poison → Bug
  sub_type: Bug → Poison

Fixing Fuzzlet (毛毛):
  sub_type: None → Cute

Fixing Swarmlet (一窝蜂):
  main_type: Flying → Bug
  sub_type: Bug → Flying
  default_legacy_type: Flying → Bug (align to main_type)

...

Summary:
  Fixed: 57 monsters
  Skipped: 61 monsters (not in Excel)

Found 57 monster(s) with type mismatches.
Apply these fixes? (yes/no): yes

Creating backup...
  Backup saved: monsters.json.backup_20251218_102030

Saving updated monsters.json...
  ✓ Saved successfully

Saving change log...
  Change log saved: type_fixes_log_20251218_102030.json

================================================================================
✓ Type fixes applied successfully!
================================================================================
```

## Default Legacy Type Rules

The script applies the following rules for `default_legacy_type`:

1. **Leader Monsters** (`is_leader_form: true`):
   - `default_legacy_type` = `"Leader"` (always)

2. **Non-Leader Monsters** (`is_leader_form: false`):
   - `default_legacy_type` = `main_type` (aligned with corrected main type)

**Example**: If a monster has `main_type: Bug`, its `default_legacy_type` should also be `Bug`, not `Poison` or `Flying`.

## Common Type Issues Fixed

### Swapped Primary/Secondary Types

Many monsters have their main_type and sub_type swapped:
- **Hornspike**: JSON has Poison/Bug → Should be Bug/Poison
- **Sprigbug**: JSON has Grass/Bug → Should be Bug/Grass
- **Swarmlet**: JSON has Flying/Bug → Should be Bug/Flying

### Missing Secondary Types

Some monsters are missing their sub_type:
- **Fuzzlet**: JSON has no sub_type → Should have Cute
- **Crawler**: JSON has no sub_type → Should have Cute
- **Dynayen**: JSON has no sub_type → Should have Fighting

### Wrong Primary Types

Some monsters have incorrect primary types:
- **Verdling**: JSON has Illusion primary → Should be Grass primary
- **Mildgull**: JSON has Water primary → Should be Flying primary

### Misaligned Legacy Types

When `main_type` changes, `default_legacy_type` must be updated to match:
- **Swarmlet**: When main_type changes from Flying → Bug, default_legacy_type also changes from Flying → Bug
- **Verdling**: When main_type changes from Illusion → Grass, default_legacy_type also changes from Illusion → Grass
- **Hornspike**: When main_type changes from Poison → Bug, default_legacy_type also changes from Poison → Bug

**Leader Exception**: Leader monsters always have `default_legacy_type: "Leader"` regardless of their main_type.

## Type Mapping

The script uses the following Chinese → English type mapping from `types.json`:

| Chinese | English |
|---------|---------|
| 普通 | Normal |
| 草 | Grass |
| 火 | Fire |
| 水 | Water |
| 光 | Light |
| 地 | Ground |
| 冰 | Ice |
| 龙 | Dragon |
| 电 | Electric |
| 毒 | Poison |
| 虫 | Bug |
| 武 | Fighting |
| 翼 | Flying |
| 萌 | Cute |
| 幽 | Ghost |
| 恶 | Dark |
| 机械 | Mechanical |
| 幻 | Illusion |
| 首领 | Leader |

## Safety Features

1. **Backup Creation**: Automatically creates timestamped backup before any changes
2. **Confirmation Required**: Must type "yes" to apply changes
3. **Change Log**: All modifications logged in JSON format for review
4. **Non-Destructive**: Only updates type fields, preserves all other data

## Files Generated

After running the script, you'll find:

```
backend/data/
├── monsters.json                          # Updated with correct types
├── monsters.json.backup_20251218_102030   # Original backup
└── type_fixes_log_20251218_102030.json    # Detailed change log
```

## Change Log Format

The change log contains:

```json
{
  "timestamp": "20251218_102030",
  "total_changes": 66,
  "changes": [
    {
      "english_name": "Hornspike",
      "zh_name": "尖角蜘蛛",
      "zh_form": null,
      "excel_row": 259,
      "changes": [
        {
          "field": "main_type",
          "old": "Poison",
          "new": "Bug"
        },
        {
          "field": "sub_type",
          "old": "Bug",
          "new": "Poison"
        }
      ]
    }
  ]
}
```

## Troubleshooting

### Script shows no fixes needed

If the script reports no type mismatches:
```
✓ No type mismatches found - monsters.json is already correct!
```

This means all monster types already match the Excel source.

### Monster not found in Excel

Monsters that exist in JSON but not in Excel will be skipped:
```
Skipped: 61 monsters (not in Excel)
```

This is expected for monsters that haven't been added to Excel yet.

### Type not in mapping

If you see a Chinese type name that isn't mapped to English, the script will use the Chinese name as-is. Update the `type_mapping` dictionary in the script if needed.

## When to Run

Run this script when:
- After updating monster data in Excel
- After importing new monsters
- When validation reports type mismatches
- Before deploying to production

## Verification

After running the script, verify the changes:

```bash
# Run validation again to confirm fixes
python3 -m backend.scripts.validation.check_source_correctness

# Check the change log
cat backend/data/type_fixes_log_*.json | jq '.total_changes'
```

## Rollback

To undo changes, restore from the backup:

```bash
# Find the backup
ls -lt backend/data/monsters.json.backup_*

# Restore from backup
cp backend/data/monsters.json.backup_YYYYMMDD_HHMMSS backend/data/monsters.json
```
