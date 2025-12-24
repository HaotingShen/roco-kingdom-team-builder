#!/usr/bin/env python3
"""
Run All Validation Checks

This script runs all validation checks in sequence and provides a comprehensive summary.

Runs:
1. check_frontend_images.py - Validates frontend image files
2. check_local_consistency.py - Validates local JSON files against each other
3. check_source_correctness.py - Validates local JSON files against Excel source
"""

import sys
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Tuple


class Colors:
    """ANSI color codes for terminal output."""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_header(title: str):
    """Print a formatted section header."""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{title.center(80)}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}\n")


def run_script(script_name: str, script_path: Path) -> Tuple[int, str]:
    """Run a validation script and return its exit code and output."""
    print(f"{Colors.BOLD}Running {script_name}...{Colors.RESET}\n")

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=script_path.parent.parent.parent,  # Project root
            capture_output=True,
            text=True
        )
        # Print the output in real-time
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)

        return result.returncode, result.stdout
    except Exception as e:
        error_msg = f"{Colors.RED}Error running {script_name}: {e}{Colors.RESET}"
        print(error_msg)
        return 1, error_msg


def save_combined_report(results: dict, outputs: dict, script_dir: Path) -> Path:
    """Save a combined validation report from all scripts."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = script_dir.parent.parent / "data" / f"combined_validation_report_{timestamp}.txt"

    with open(report_path, 'w', encoding='utf-8') as f:
        # Header
        f.write("="*80 + "\n")
        f.write("COMBINED VALIDATION REPORT - ALL CHECKS\n")
        f.write("="*80 + "\n\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        # Overall summary
        f.write("="*80 + "\n")
        f.write("OVERALL SUMMARY\n")
        f.write("="*80 + "\n\n")

        all_passed = all(code == 0 for code in results.values())
        passed_count = sum(1 for code in results.values() if code == 0)
        failed_count = len(results) - passed_count

        f.write(f"Total Checks: {len(results)}\n")
        f.write(f"Passed: {passed_count}\n")
        f.write(f"Failed: {failed_count}\n\n")

        f.write("Individual Results:\n")
        for script_name, exit_code in results.items():
            status = "PASSED ✓" if exit_code == 0 else "FAILED ✗"
            f.write(f"  - {script_name}: {status}\n")

        f.write("\n")

        if all_passed:
            f.write("✅ ALL VALIDATION CHECKS PASSED!\n\n")
        else:
            f.write(f"❌ {failed_count} VALIDATION CHECK(S) FAILED\n\n")

        # Detailed output from each script
        f.write("="*80 + "\n")
        f.write("DETAILED OUTPUT FROM EACH CHECK\n")
        f.write("="*80 + "\n\n")

        for script_name, output in outputs.items():
            f.write("-"*80 + "\n")
            f.write(f"{script_name}\n")
            f.write("-"*80 + "\n\n")

            # Remove ANSI color codes for the text report
            clean_output = output
            for code in ['\033[91m', '\033[92m', '\033[93m', '\033[94m', '\033[95m',
                        '\033[96m', '\033[0m', '\033[1m']:
                clean_output = clean_output.replace(code, '')

            f.write(clean_output)
            f.write("\n\n")

        # Footer
        f.write("="*80 + "\n")
        f.write("END OF COMBINED VALIDATION REPORT\n")
        f.write("="*80 + "\n")

    return report_path


def main():
    """Main entry point."""
    script_dir = Path(__file__).parent

    # Define validation scripts in order
    scripts = [
        ("Frontend Images Check", script_dir / "check_frontend_images.py"),
        ("Local Consistency Check", script_dir / "check_local_consistency.py"),
        ("Source Correctness Check", script_dir / "check_source_correctness.py"),
    ]

    # Print overall header
    print_header("COMPREHENSIVE DATA VALIDATION")
    print(f"{Colors.BOLD}Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.RESET}\n")

    # Track results and outputs
    results = {}
    outputs = {}

    # Run each script
    for script_name, script_path in scripts:
        if not script_path.exists():
            print(f"{Colors.RED}✗ Script not found: {script_path}{Colors.RESET}\n")
            results[script_name] = 1
            outputs[script_name] = f"Error: Script not found at {script_path}"
            continue

        print_header(script_name)
        exit_code, output = run_script(script_name, script_path)
        results[script_name] = exit_code
        outputs[script_name] = output

        # Print result for this script
        if exit_code == 0:
            print(f"\n{Colors.GREEN}✓ {script_name} PASSED{Colors.RESET}")
        else:
            print(f"\n{Colors.RED}✗ {script_name} FAILED{Colors.RESET}")

    # Print overall summary
    print_header("OVERALL SUMMARY")

    all_passed = all(code == 0 for code in results.values())

    print(f"{Colors.BOLD}Results:{Colors.RESET}\n")
    for script_name, exit_code in results.items():
        status_color = Colors.GREEN if exit_code == 0 else Colors.RED
        status_text = "PASSED" if exit_code == 0 else "FAILED"
        print(f"  {status_color}{'✓' if exit_code == 0 else '✗'} {script_name}: {status_text}{Colors.RESET}")

    # Save combined report
    report_path = save_combined_report(results, outputs, script_dir)

    print(f"\n{Colors.BOLD}{'='*80}{Colors.RESET}")

    if all_passed:
        print(f"{Colors.BOLD}{Colors.GREEN}✅ ALL VALIDATION CHECKS PASSED!{Colors.RESET}")
        exit_code = 0
    else:
        failed_count = sum(1 for code in results.values() if code != 0)
        print(f"{Colors.BOLD}{Colors.RED}❌ {failed_count} VALIDATION CHECK(S) FAILED{Colors.RESET}")
        exit_code = 1

    print(f"{Colors.BOLD}{'='*80}{Colors.RESET}\n")
    print(f"{Colors.BOLD}Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}Combined report saved to: {report_path.name}{Colors.RESET}\n")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
