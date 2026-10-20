"""Development checks for feature scope, control context and glass-string intent.

These exposed cases check routing and source boundaries. They are not an
independent RQ2 evaluation or a measure of unrestricted language understanding.
"""
from __future__ import annotations

import copy
import re
import unittest

from graph_inference import resolve_feature
from wautrace_engine import WauTraceEngine


def case(case_id, question, profiles, status, *, setup=(), edges=(), forbidden_profiles=(), contains=()):
    return {"case_id": case_id, "question": question, "setup": list(setup),
            "acceptable_profiles": [profiles] if isinstance(profiles, str) else list(profiles),
            "allowed_statuses": [status] if isinstance(status, str) else list(status),
            "required_edge_ids": list(edges), "forbidden_profiles": list(forbidden_profiles),
            "required_text_patterns": list(contains)}


FORMS = ("What forms does Wau Kikik have?",)
CLASS = ("Do most Malay kites have leaf-shaped wings?",)
CASES = [
    case("CLASS-01", "Do most Malay kites have leaf-shaped wings?", "class_wings", "supported", edges=("E077",), contains=(r"most",)),
    case("CLASS-02", "Do most traditional Malay wau have leaf-shaped wings?", "class_wings", "supported", edges=("E077",)),
    case("CLASS-03", "Do most Malay kites have leaf-shaped wings?", "class_wings", "supported", setup=FORMS, edges=("E077",)),
    case("CLASS-04", "Do most Malay kites have leaf-shaped wings?", "class_wings", "supported", setup=("Is Wau Laga hard to fly?",), edges=("E077",)),
    case("CLASS-05", "Do most Malay kites have a hummer?", [None], ["clarification", "not_documented"], forbidden_profiles=("form_comparison_unknown", "hummer")),
    case("CLASS-06", "Do most Malay kites have sobek carvings?", [None], ["clarification", "not_documented"], forbidden_profiles=("form_comparison_unknown", "sobek")),
    case("CLASS-07", "Does Wau Kikik have leaf-shaped wings?", "wings", "explicit_negative", setup=CLASS, edges=("E029", "E077")),
    case("CLASS-08", "Does Wau Kikik have them?", "wings", "explicit_negative", setup=CLASS, edges=("E029", "E077")),
    case("CLASS-09", "Why not?", "exclusion_reason", "not_documented", setup=CLASS+("Does Wau Kikik have them?",), edges=("E029", "E077")),
    case("CLASS-10", "Does Wau Bulan have leaf-shaped wings?", [None, "source_unknown"], ["clarification", "not_documented"], forbidden_profiles=("wings", "class_wings", "form_comparison_unknown")),
    case("RANK-01", "Which form is most popular?", "form_comparison_unknown", "not_documented", setup=FORMS, edges=("E016",)),
    case("RANK-02", "Which Wau Kikik type is the most common?", "form_comparison_unknown", "not_documented", edges=("E016",)),
    case("RANK-03", "What is the most important feature of Wau Kikik?", [], ["supported", "not_documented", "clarification"], forbidden_profiles=("form_comparison_unknown", "attack_speed")),
    case("RANK-04", "Do most Wau Kikik forms have leaf-shaped wings?", "wings", "explicit_negative", edges=("E029",), forbidden_profiles=("form_comparison_unknown",)),
    case("RANK-05", "Do most Wau Kikik forms have a hummer?", "hummer", "explicit_negative", edges=("E007",), forbidden_profiles=("form_comparison_unknown",)),
    case("RANK-06", "Do most Wau Kikik forms have sobek carvings?", "sobek", "explicit_negative", edges=("E008",), forbidden_profiles=("form_comparison_unknown",)),
    case("CONTROL-01", "Why is it hard to control the kite when it is close to me?", "wind", "supported", edges=("E047", "E072")),
    case("CONTROL-02", "Is it hard to control Wau Laga near the player?", "wind", "supported", edges=("E047", "E072")),
    case("CONTROL-03", "Why is Wau Laga difficult to control close to the player?", "wind", "supported", setup=FORMS, edges=("E047", "E072")),
    case("CONTROL-04", "Why does the kite rotate in strong wind near the player?", "wind", "supported", edges=("E047", "E072")),
    case("CONTROL-05", "Is Wau Laga hard to fly?", "skill", "supported", edges=("E031", "E032")),
    case("CONTROL-06", "What makes Wau Laga difficult?", "skill", "supported", edges=("E031", "E032")),
    case("GLASS-01", "Tell me about the glass string", ["kaca_reason", "laga_glass"], "supported", contains=(r"glass", r"string")),
    case("GLASS-02", "How is the glass string made?", "glass_recipe", "not_documented", contains=(r"not.*(?:recipe|preparation)|do not provide",)),
    case("GLASS-03", "Describe the glass-coated kite string", ["kaca_reason", "laga_glass"], "supported"),
    case("GLASS-04", "How do they prepare the glass-coated string?", "glass_recipe", "not_documented"),
    case("GLASS-05", "Tell me about the glass string", ["kaca_reason", "laga_glass"], "supported", setup=FORMS),
    case("GLASS-06", "How is the glass string made?", "glass_recipe", "not_documented", setup=("Is Wau Laga hard to fly?",)),
    case("GLASS-07", "Is Wau Kaca made of glass?", "kaca_body", "supported"),
    case("GLASS-08", "Do all of them still use that kind of string today?", ["glass_current", "laga_glass_current"], "not_documented", setup=("Why is it called Wau Kaca?",)),
    case("COMPARISON-01", "What is the Malay Kite?", "eddy", "supported", edges=("E028",)),
]


def run_case(engine, specification):
    state = {}
    for question in specification["setup"]:
        state = engine.respond(question, copy.deepcopy(state))["state"]
    response = engine.respond(specification["question"], copy.deepcopy(state))
    profile = response["routing"].get("selected_profile")
    errors = []
    if response["status"] not in specification["allowed_statuses"]:
        errors.append("Evidence state does not fit the requested scope.")
    if specification["acceptable_profiles"] and profile not in specification["acceptable_profiles"]:
        errors.append("The response answers a different relation or entity.")
    if profile in specification["forbidden_profiles"]:
        errors.append("An inapplicable comparison or subtype response was selected.")
    if not set(specification["required_edge_ids"]) <= set(response["edge_ids"]):
        errors.append("Required evidence edges are missing.")
    for pattern in specification["required_text_patterns"]:
        if not re.search(pattern, response["text"], re.I):
            errors.append("Required scope wording is missing: " + pattern)
    if response["status"] in {"supported", "explicit_negative", "source_variance"} and not response["source_cards"]:
        errors.append("A substantive answer has no source cards.")
    for card in response["source_cards"]:
        for edge_id in card["edge_ids"]:
            if edge_id not in response["edge_ids"] or not any(
                all(evidence.get(key) == card[key] for key in ("source_id", "page", "language", "quote"))
                for evidence in engine.edges[edge_id]["evidence"]
            ):
                errors.append("A source card differs from its selected evidence.")
    if profile == "class_wings":
        graph = response["routing"].get("graph_inference", {})
        if graph.get("quantifier") != "most" or graph.get("inherited_as_subtype_fact") is not False:
            errors.append("The class-most statement lost its qualification.")
    if profile == "wings":
        graph = response["routing"].get("graph_inference", {})
        if graph.get("class_candidate_action") != "overridden_for_subtype_answer" or graph.get("value") is not False:
            errors.append("Direct subtype negation did not override the class context.")
    return {"case_id": specification["case_id"], "question": specification["question"],
            "setup": specification["setup"], "response": response, "failures": errors,
            "passed": not errors}


class ScopeRoutingChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = WauTraceEngine()

    def test_requested_cases_and_context_contrasts(self):
        for specification in CASES:
            with self.subTest(case_id=specification["case_id"]):
                result = run_case(self.engine, specification)
                self.assertEqual(result["failures"], [], result)

    def test_class_frequency_does_not_establish_an_undocumented_subtype_feature(self):
        result = resolve_feature(self.engine.network, "wau_laga_named_type", "leaf_shaped_wings")
        self.assertEqual(result["status"], "not_documented")
        self.assertIsNone(result["value"])
        self.assertFalse(result["inherited_as_subtype_fact"])
        self.assertIn("E077", result["class_context_edge_ids"])
        self.assertEqual(result["class_candidate_action"], "context_only_not_inherited")

    def test_explicit_feature_question_overrides_stale_form_comparison(self):
        state = self.engine.respond("Which Wau Kikik form is the most popular?")["state"]
        response = self.engine.respond("Does Wau Kikik have a hummer?", state)
        self.assertEqual(response["routing"].get("selected_profile"), "hummer")
        self.assertEqual(response["status"], "explicit_negative")
        self.assertIn("E007", response["edge_ids"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
