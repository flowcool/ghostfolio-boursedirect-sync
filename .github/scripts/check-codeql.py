"""Enforce the repository CodeQL thresholds on this analysis, before merge."""

import json
import sys
from pathlib import Path


def main() -> int:
    files = sorted(Path(sys.argv[1]).glob("*.sarif"))
    if not files:
        raise ValueError("CodeQL produced no SARIF report")
    findings = []
    runs = 0
    for path in files:
        report = json.loads(path.read_text())
        for run in report["runs"]:
            runs += 1
            driver = run["tool"]["driver"]
            if driver["name"] != "CodeQL":
                raise ValueError("Expected CodeQL SARIF")
            rules = {rule["id"]: rule for rule in driver.get("rules", [])}
            for result in run.get("results", []):
                if any(s.get("status") == "accepted" for s in result.get("suppressions", [])):
                    continue
                rule = rules[result["ruleId"]]
                level = result.get("level", rule.get("defaultConfiguration", {}).get("level", "warning"))
                severity = rule.get("properties", {}).get("security-severity")
                if level == "error" or (severity is not None and float(severity) >= 4.0):
                    findings.append(result["ruleId"])
    if not runs:
        raise ValueError("CodeQL produced no analysis runs")
    if findings:
        print("Blocking CodeQL findings: " + ", ".join(sorted(set(findings))))
        return 1
    print("CodeQL thresholds passed: errors and medium-or-higher security findings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
