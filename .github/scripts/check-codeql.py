"""Enforce the repository CodeQL thresholds on this analysis, before merge."""

import json
import sys
from pathlib import Path


def result_rule(tool: dict, result: dict) -> dict:
    reference = result.get("rule", {})
    component_ref = reference.get("toolComponent", {})
    if "index" in component_ref:
        extensions = tool.get("extensions", [])
        index = component_ref["index"]
        if type(index) is not int or index < 0 or index >= len(extensions):
            raise ValueError(f"Invalid CodeQL component index: {index}")
        component = extensions[index]
    elif component_ref:
        matches = [c for c in [tool["driver"], *tool.get("extensions", [])]
                   if all(c.get(k) == v for k, v in component_ref.items())]
        if len(matches) != 1:
            raise ValueError("Cannot resolve CodeQL rule component")
        component = matches[0]
    else:
        component = tool["driver"]
    rules = component.get("rules", [])
    rule_id = result.get("ruleId", reference.get("id"))
    index = reference.get("index", result.get("ruleIndex"))
    if index is not None:
        if type(index) is not int or index < 0 or index >= len(rules):
            raise ValueError(f"Invalid CodeQL rule index: {index}")
        rule = rules[index]
        if rule_id is not None and rule["id"] != rule_id:
            raise ValueError("CodeQL rule index and ID disagree")
        return rule
    matches = [r for r in rules if r["id"] == rule_id]
    if len(matches) != 1:
        raise ValueError(f"Cannot resolve CodeQL rule: {rule_id}")
    return matches[0]


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
            if not driver["name"].startswith("CodeQL"):
                raise ValueError("Expected CodeQL SARIF")
            for result in run.get("results", []):
                if any(s.get("status") == "accepted" for s in result.get("suppressions", [])):
                    continue
                rule = result_rule(run["tool"], result)
                level = result.get("level", rule.get("defaultConfiguration", {}).get("level", "warning"))
                severity = rule.get("properties", {}).get("security-severity")
                if level == "error" or (severity is not None and float(severity) >= 4.0):
                    findings.append(rule["id"])
    if not runs:
        raise ValueError("CodeQL produced no analysis runs")
    if findings:
        print("Blocking CodeQL findings: " + ", ".join(sorted(set(findings))))
        return 1
    print("CodeQL thresholds passed: errors and medium-or-higher security findings")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, ValueError, TypeError, IndexError) as error:
        print(f"Cannot evaluate CodeQL report: {error}", file=sys.stderr)
        raise SystemExit(2) from error
