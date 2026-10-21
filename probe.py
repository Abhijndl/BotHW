#!/usr/bin/env python3
"""Probe #20: run the real case-table refresher (cases.py) on GitHub and keep
the hw_cases.json it builds (as probe_report.json)."""
import os, runpy, shutil, time
t0 = time.time()
os.environ["HW_CASES_FILE"] = "hw_cases.json"
try:
    runpy.run_path("cases.py", run_name="__main__")
except SystemExit as e:
    print("cases.py exit:", e.code)
shutil.copy("hw_cases.json", "probe_report.json")
print(f"done in {time.time() - t0:.0f}s")
