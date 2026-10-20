"""Content hashes for the development regression inputs and rubric."""
from __future__ import annotations
import hashlib
import json


def content_digest(value):
    data = json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def input_payload(scenarios):
    return [{
        **{key: case[key] for key in
           ("test_id", "category", "initial_context", "linguistic_variation")},
        "inputs": [{key: turn[key] for key in
                    ("turn_number", "input_type", "input")}
                   for turn in case["inputs"]],
    } for case in scenarios["scenarios"]]


def semantic_payload(scenarios):
    """Include the development rubric; omit display labels and execution outputs.

    This projection includes the development inputs, expected behaviour, evidence
    scope, intent expectations and all pass criteria. Category display labels,
    execution-result fields and current-build metadata are outside it.
    """
    rubric_keys = ("test_id", "title", "expected_behaviour", "allowed_record_ids",
                   "allowed_evidence", "allowed_pages", "allowed_non_paginated_sources",
                   "pass_criteria", "interpretation_note")
    return {
        "inputs": input_payload(scenarios),
        "category_counts": [{key: group[key] for key in ("category", "planned_cases")}
                            for group in scenarios["category_counts"]],
        "evaluation_contract": scenarios["evaluation_contract"],
        "rubric": [{
            **{key: case[key] for key in rubric_keys if key in case},
            "turns": [{key: value for key, value in turn.items()
                       if key not in {"input", "input_type", "actual_output"}}
                      for turn in case["inputs"]],
        } for case in scenarios["scenarios"]],
    }
