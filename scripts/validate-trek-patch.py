#!/usr/bin/env python3
"""Validate the feed and the behavior our Star Trek patch must preserve."""

import json
from pathlib import Path

CONDITION = "inputs.sorting.aiUpscaleTrek == boost or inputs.sortingP2P.aiUpscaleTrek == boost"
SCOPE = "/*Trek AI Upscale*/ queryType == 'series' and title in ['Star Trek: Deep Space Nine', 'Star Trek: Voyager'] ? "
EXPRESSIONS = {
    "preferredStreamExpressions": SCOPE + "regexMatched(negate(type(uncached(streams),'debrid'), streams), 'Upscaled') : []",
    "includedStreamExpressions": SCOPE + "passthrough(regexMatched(streams, 'Upscaled'), 'excluded') : []",
    "rankedStreamExpressions": SCOPE + "regexMatched(streams, 'Upscaled') : []",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(feed):
    require(isinstance(feed, list), "Template feed must be a list")
    templates = [t for t in feed if t.get("metadata", {}).get("id") == "tamtaro.complete"]
    require(len(templates) == 1, "Expected exactly one tamtaro.complete template")
    template = templates[0]
    inputs = template["metadata"]["inputs"]
    for group_id in ("sorting", "sortingP2P"):
        groups = [g for g in inputs if g.get("id") == group_id]
        require(len(groups) == 1, f"Missing or duplicate {group_id} group")
        controls = [c for c in groups[0]["subOptions"] if c.get("id") == "aiUpscaleTrek"]
        require(len(controls) == 1, f"Missing or duplicate upscale control in {group_id}")
        control = controls[0]
        require(control.get("type") == "select" and control.get("default") == "boost", f"Changed upscale default in {group_id}")
        require({o["value"] for o in control["options"]} == {"boost", "none"}, f"Changed upscale choices in {group_id}")

    config = template["config"]
    for key, expression in EXPRESSIONS.items():
        entries = config[key]["__value"] if key == "rankedStreamExpressions" else config[key]
        matches = [e for e in entries if e.get("expression") == expression]
        require(len(matches) == 1, f"Missing or duplicate Trek expression in {key}")
        entry = matches[0]
        require(entry.get("__if") == CONDITION and entry.get("enabled") is True, f"Changed Trek expression condition in {key}")
        if key == "rankedStreamExpressions":
            require(entry.get("score") == 10000, "Changed upscale penalty cancellation score")
        if key == "preferredStreamExpressions":
            index = entries.index(entry)
            require(all(index < i for i, e in enumerate(entries) if "<SYNCED:" in e.get("expression", "")), "Trek preference must precede synced preferences")


if __name__ == "__main__":
    path = Path(__file__).resolve().parents[1] / "Tamtaro-All-Templates-for-AIOStreams.json"
    validate(json.loads(path.read_text()))
    print("Template JSON and DS9/Voyager upscale patch validated.")
