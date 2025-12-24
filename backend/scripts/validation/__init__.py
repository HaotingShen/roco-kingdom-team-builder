"""
Data validation package for Roco Kingdom Team Builder.

This package contains scripts to validate data consistency and correctness:
- check_local_consistency.py: Validates local JSON files against each other
- check_source_correctness.py: Validates local JSON files against data_all.xlsx
- run_all_checks.py: Runs all validation checks in sequence
"""

__version__ = "1.0.0"
__all__ = ["check_local_consistency", "check_source_correctness", "run_all_checks"]
