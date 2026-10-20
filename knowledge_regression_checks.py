#!/usr/bin/env python3
"""Check source scopes and graph answer contracts, not bot accuracy.

Run: python knowledge_regression_checks.py
These checks concern graph semantics and are separate from language-understanding evaluation.
Only Python's standard library is required.
"""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from graph_inference import deduplicate_answers, resolve_feature

BASE = Path(__file__).resolve().parent


def main():
    network_path = BASE / "WauTrace_Network_Template.json"
    network = json.loads(network_path.read_text(encoding="utf-8"))
    edges = {edge["edge_id"]: edge for edge in network["edges"]}
    rows = []

    def check(check_id, condition, detail):
        rows.append({"check": check_id, "result": "pass" if condition else "fail",
                     "detail": detail})

    def quotes(edge_id, page, language=None):
        return [q["quote"] for q in edges[edge_id]["evidence"]
                if q["page"] == page and (language is None or q["language"] == language)]

    check("controlling_heading", all(
        "The technic of controlling Wau Laga, p.146" in edges[eid]["scope"]
        and "Guidelines" not in edges[eid]["scope"] for eid in ("E047", "E048")),
        "The proximity and height claims refer to the first p.146 subsection.")
    guideline_edges = [edge for edge in edges.values() if "Guidelines" in edge["scope"]]
    check("guidelines_heading", bool(guideline_edges) and all(
        "Guidelines to control the Wau Laga" in edge["scope"] for edge in guideline_edges),
        "The second subsection retains the exact article in its title.")
    check("complete_malay_negative", any(
        quote.startswith("Wau Kikik tidak mempunyai busur") for quote in quotes("E007", 72, "ms")),
        "The Malay hummer/busur quotation begins with the complete name.")
    labels = {edge["object_value"] for edge in edges.values()
              if edge["record_id"] == "RQ1-P05" and edge["relation"] == "has_source_role_label"}
    check("launch_role_labels", {"juru anjong", "juru main tali", "juru lancar", "juru tarik"} <= labels,
        "All four source labels are represented under the two-player launch record.")
    check("two_players_not_four", any(
        edge["record_id"] == "RQ1-P05" and edge["object_type"] == "number"
        and edge["object_value"] == 2 for edge in edges.values())
        and not any(edge["record_id"] == "RQ1-P05" and edge["object_type"] == "number"
                    and edge["object_value"] == 4 for edge in edges.values()),
        "Role labels do not create a four-player factual assertion.")
    check("glass_competitive_purpose", all(
        edges[eid]["relation"] == "has_source_competitive_purpose"
        and edges[eid]["subject"] == subject and bool(quotes(eid, page))
        for eid, subject, page in (("E073", "powdered_glass_on_string", 73),
                                   ("E074", "powdered_glass_on_string", 72),
                                   ("E068", "glass_glazed_string", 144))),
        "The naming profile and practice section retain their distinct purpose evidence.")
    check("glass_answer_scope", "cut" in edges["E035"]["answer_en"].lower()
        and "normally" in edges["E035"]["answer_en"].lower()
        and "contact" in edges["E073"]["object_value"].lower(),
        "The normal-practice qualifier and the English contact condition remain explicit.")
    check("launch_ground_preparation", edges["E071"]["record_id"] == "RQ1-P07"
        and edges["E071"]["subject"] == "wau_laga_launch"
        and "ground" in edges["E071"]["object_value"] and bool(quotes("E071", 144)),
        "Laying rolled string on the ground is represented in launch preparation on p.144.")
    wind = edges["E072"]
    check("wind_movement_qualifiers", "left or right" in wind["object_value"]
        and any(word in wind["object_value"].lower() for word in ("possible", "may", "might"))
        and "too close" in wind["scope"] and "strong wind" in wind["object_value"],
        "Side movement and possible rotation retain proximity and strong-wind conditions.")
    check("attack_objective_additional_page", all(
        any("before it breaks yours" in quote for quote in quotes(eid, 148))
        for eid in ("E033", "E034")),
        "Both competition objectives retain the additional p.148 source sentence.")

    duplicate_pair = [edges["E052"], edges["E012"]]
    answers = deduplicate_answers(duplicate_pair)
    check("one_defence_answer", len(answers) == 1 and answers[0]["canonical_answer_edge_id"] == "E012"
        and answers[0]["answer_en"] == edges["E012"]["answer_en"]
        and answers[0]["source_edge_ids"] == ["E012", "E052"]
        and set(answers[0]["record_ids"]) == {"RQ1-S09", "RQ1-P09"}
        and "E065" in answers[0]["required_context_edge_ids"]
        and len(answers[0]["evidence"]) == 1,
        "One conditional answer keeps both record references, the shared quote and attack context.")
    opposite = deepcopy(edges["E052"])
    opposite.update(edge_id="REGRESSION-OPPOSITE", polarity="negative", status="explicit_negative")
    check("dedup_preserves_opposition", len(deduplicate_answers([edges["E012"], opposite])) == 2,
        "A synthetic opposite-polarity probe cannot be hidden by presentation deduplication.")
    check("dedup_order_independent", deduplicate_answers(list(reversed(duplicate_pair))) == answers,
        "Canonical answer selection and merged provenance do not depend on retrieval order.")

    kikik = resolve_feature(network, "wau_kikik", "leaf_shaped_wings")
    check("explicit_subtype_exception", kikik["status"] == "explicit_negative"
        and kikik["value"] is False and kikik["class_context_edge_ids"] == ["E077"],
        "The direct Kikik negative controls its answer while retaining qualified class context.")
    laga = resolve_feature(network, "wau_laga_named_type", "leaf_shaped_wings")
    check("no_universal_inheritance", laga["status"] == "not_documented"
        and laga["value"] is None and not laga["inherited_as_subtype_fact"],
        "A class-most statement does not manufacture a Laga feature claim.")
    category = resolve_feature(network, "traditional_malay_wau", "leaf_shaped_wings")
    check("class_majority_qualified", category["status"] == "supported" and category["quantifier"] == "most",
        "A query about the class reports the documented non-universal quantifier.")

    check("pending_operational_author_review", network["author_review"]["status"] == "record_evidence_documented_edge_review_pending"
        and network["author_review"]["approved_edges"] == 0
        and all(edge["author_decision"] == "pending" and edge.get("author_reviewer") is None
                for edge in edges.values()),
        "Source checks do not constitute per-edge operational author approval.")
    check("english_operational_metadata", not re.search(r"[\u0600-\u06ff]", network_path.read_text(encoding="utf-8")),
        "Operational metadata is English; original Malay source quotations remain verbatim.")
    failures = [row for row in rows if row["result"] == "fail"]
    report = {"validation_kind": "knowledge_and_retrieval_regression",
              "validated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "result": "fail" if failures else "pass", "checks_count": len(rows),
              "failed_checks": len(failures), "network_sha256": hashlib.sha256(network_path.read_bytes()).hexdigest(),
              "bot_tests_executed": False, "performance_results_claimed": False, "study_ready": False,
              "author_edge_review": "pending",
              "synthetic_probe_scope": "Only dedup_preserves_opposition uses an in-memory synthetic edge; it is never saved to the knowledge base.",
              "checks": rows}
    (BASE / "knowledge_regression_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{report['result'].upper()}: {len(rows)} knowledge/retrieval checks; {len(failures)} failures. No chatbot scenarios were run.")
    for row in failures:
        print(f"FAIL: {row['check']} — {row['detail']}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
