"""Known development acceptance checks for scoped answers and follow-up context.

These cases are exposed development material. They do not estimate independent
RQ2 accuracy. Expected source edges and answer boundaries are fixed before the
current routing implementation is executed against them.
"""
from __future__ import annotations

import copy
import re
import unittest

from wautrace_engine import WauTraceEngine


def case(case_id, question, profiles, status, *, setup=(), edges=(), contains=(), excludes=()):
    return {"case_id": case_id, "question": question, "setup": list(setup),
            "acceptable_profiles": [profiles] if isinstance(profiles, str) else list(profiles),
            "expected_status": status, "required_edge_ids": list(edges),
            "required_text_patterns": list(contains), "forbidden_text_patterns": list(excludes)}


KIKIK = ("What is Wau Kikik?",)
FORMS = ("What forms does Wau Kikik have?",)
HEIGHT = ("How high does Wau Laga fly in the book?",)
CASES = [
    case("A1-known", "why is it important ?", "importance_overview", "supported", setup=KIKIK, edges=("E027",), contains=(r"reason|explain",), excludes=(r"speed.*crucial",)),
    case("A1-unclear", "why is it important ?", [None], "clarification", excludes=(r"speed.*crucial",)),
    case("A1-significant", "Why is Wau Kikik significant?", "importance_overview", "supported", edges=("E027",), contains=(r"reason|explain",)),
    case("A1-special", "Why is Wau Kikik special?", "importance_overview", "supported", edges=("E027",), contains=(r"reason|explain",)),
    case("A1-crucial-contrast", "What is crucial when attacking an opponent's kite?", "attack_speed", "supported"),
    case("A2-first-use", "when did this wau first used ?", "origin", "not_documented", setup=("How many people launch Wau Laga?",), contains=(r"first.*us|invent",), excludes=(r"signals.*launcher",)),
    case("A2-since", "Since when has Wau Kikik existed?", "origin", "not_documented"),
    case("A2-how-old", "How old is Wau Kikik?", "origin", "not_documented"),
    case("A2-how-long", "How long has Wau Kikik been used?", "origin", "not_documented"),
    case("A2-year", "What year was Wau Kikik first flown?", "origin", "not_documented"),
    case("A3-at-first-place", "what is wau at the first place ?", "wau_definition", "supported", contains=(r"kite",), excludes=(r"place-specific",)),
    case("A3-in-first-place", "what is a wau in the first place?", "wau_definition", "supported", contains=(r"kite",), excludes=(r"place-specific",)),
    case("A4-popular", "which form is more popular ?", "form_comparison_unknown", "not_documented", setup=FORMS, edges=("E016",), contains=(r"rank",), excludes=(r"place-specific",)),
    case("A4-important", "which form is more important ?", "form_comparison_unknown", "not_documented", setup=FORMS, edges=("E016",), excludes=(r"speed.*crucial",)),
    case("A4-best", "Which form of Wau Kikik is the best?", "form_comparison_unknown", "not_documented", edges=("E016",)),
    case("A4-common", "Which Wau Kikik type is most common?", "form_comparison_unknown", "not_documented", edges=("E016",)),
    case("A4-rare", "Which shape is rarest?", "form_comparison_unknown", "not_documented", setup=FORMS, edges=("E016",)),
    case("A5-three", "why does it have 3 forms ?", "form_reason", "not_documented", setup=FORMS, edges=("E016",), contains=(r"not explain",)),
    case("A5-shapes", "Why does Wau Kikik have different shapes?", "form_reason", "not_documented", edges=("E016",)),
    case("B1-tail-first", "First form", "form_component_unknown", "not_documented", setup=KIKIK+("does it have tail?",), contains=(r"first", r"tail")),
    case("B1-tail-second", "Second form", "form_tail", "supported", setup=KIKIK+("does it have tail?",), contains=(r"tail",)),
    case("B2-head-second", "Second form", "form_component_unknown", "not_documented", setup=KIKIK+("does it have a head?",), contains=(r"second", r"head")),
    case("B2-head-first", "First form", "form_head", "supported", setup=KIKIK+("does it have a head?",), contains=(r"head",)),
    case("B-geometry", "Third form", "form_3", "source_variance", setup=("What shape is Wau Kikik?",), contains=(r"square", r"rectangle|rectangular")),
    case("B-new-question", "When was Wau Kikik first used?", "origin", "not_documented", setup=("Does Wau Kikik have a tail?",)),
    case("C1-wou", "what is Wou kikik ?", "overview", "supported", edges=("E027",)),
    case("C1-kikick", "What is Wau Kikick?", "overview", "supported", edges=("E027",)),
    case("C1-possessive", "Describe Wau Kikik's forms", "form_overview", "supported", edges=("E016",)),
    case("C1-protected-name", "What is Wau Kemetek?", "kemetek", "not_documented"),
    case("D1-look", "What does Wau Kikik look like?", "form_overview", "supported", edges=("E016",)),
    case("D1-appearance", "describe its appearance", "form_overview", "supported", setup=KIKIK, edges=("E016",)),
    case("D2-kinds", "How many kinds of Wau Kikik exist?", "form_count", "supported", edges=("E016",)),
    case("D2-sorts", "How many sorts are there?", "form_count", "supported", setup=KIKIK, edges=("E016",)),
    case("D2-varieties", "How many varieties does Wau Kikik have?", "form_count", "supported", edges=("E016",)),
    case("D2-versions", "How many versions of Wau Kikik are there?", "form_count", "supported", edges=("E016",)),
    case("D3-hard", "Is Wau Laga hard to fly?", "skill", "supported", edges=("E031", "E032")),
    case("D3-difficult", "What makes Wau Laga difficult?", "skill", "supported", edges=("E031", "E032")),
    case("D3-challenging", "Is playing Laga challenging?", "skill", "supported", edges=("E031", "E032")),
    case("D4-signal", "Who gives the signal to release the kite?", "launch_signal", "supported", edges=("E045",), contains=(r"puller|juru tarik",)),
    case("D4-tells", "Who tells the launcher to release the wau?", "launch_signal", "supported", edges=("E045",)),
    case("D5-lock", "When should I lock the string?", "steer", "supported", edges=("E060", "E061", "E062")),
    case("D5-line", "when do you lock the line", "steer", "supported", edges=("E060", "E061", "E062")),
    case("D6-western", "Which western kite looks like Wau Kikik?", "eddy", "supported", edges=("E010", "E028")),
    case("D6-malay", "What is the Malay Kite?", "eddy", "supported", edges=("E028",)),
    case("D7-special", "What is special about wau kikik?", ["overview", "importance_overview", "distinctive_features"], "supported", edges=("E027",)),
    case("D7-simple", "Why is Wau Kikik considered simple?", ["overview", "importance_overview"], "supported", edges=("E027",), contains=(r"reason|explain",)),
    case("D7-characterise", "What characterises Wau Kikik?", ["overview", "importance_overview", "distinctive_features"], "supported", edges=("E027",)),
    case("D8-still", "Is it still used today?", "practice_current", "not_documented", setup=("Why is it called Wau Kaca?",), contains=(r"2002",)),
    case("D8-flown", "Is Wau Kikik still flown today?", "practice_current", "not_documented", contains=(r"2002",)),
    case("D8-currently", "Do people currently fly Wau Kikik?", "practice_current", "not_documented", contains=(r"2002",)),
    case("D9-rule", "Is that a rule?", "legal_height", "not_documented", setup=HEIGHT, contains=(r"rule|permission|regulation",)),
    case("D9-500", "Can I fly it at 500 feet?", "legal_height", "not_documented", setup=HEIGHT, contains=(r"permission|legal|regulation",)),
    case("D9-required", "Is that height required?", "legal_height", "not_documented", setup=HEIGHT),
    case("D10-hummer", "Why not?", "exclusion_reason", "not_documented", setup=("Does Wau Kikik have a hummer?",), edges=("E007",), contains=(r"reason|explain",)),
    case("D10-sobek", "Why?", "exclusion_reason", "not_documented", setup=("Does Wau Kikik have sobek carvings?",), edges=("E008",), contains=(r"reason|explain",)),
    case("D10-wings", "why not", "exclusion_reason", "not_documented", setup=("Does Wau Kikik have leaf-shaped wings?",), contains=(r"reason|explain",)),
    case("D11-next", "What happens next?", "launch_process", "supported", setup=("Who gives the signal to release the kite?",), edges=("E044", "E045", "E046", "E071")),
    case("D11-then", "And then?", "launch_process", "supported", setup=("Where is the rolled kite string placed?",), edges=("E044", "E045", "E046", "E071")),
    case("D11-after", "What happens after that?", "launch_process", "supported", setup=("Who helps launch Wau Laga?",), edges=("E044", "E045", "E046", "E071")),
    case("D12-bamboo-paper", "Is it made from bamboo and paper?", "construction_specs", "not_documented", setup=KIKIK, edges=("E030",), contains=(r"paper", r"frame|structural")),
    case("D12-frame", "Is the frame made of bamboo?", "construction_specs", "not_documented", setup=KIKIK, edges=("E030",)),
    case("D12-spars", "What wood are Wau Kikik's spars made of?", "construction_specs", "not_documented", edges=("E030",)),
    case("E1-festival", "Was Wau Kikik used in festivals?", "source_unknown", "not_documented", excludes=(r"place-specific|location|absent there",)),
    case("E1-geography", "Is Wau Laga played in Kelantan?", "place_unknown", "not_documented"),
    case("E1-outside", "Is Wau Kikik used outside Malaysia?", "place_unknown", "not_documented"),
    case("E2-cost", "How much does it cost?", [None], "not_documented", excludes=(r"does not mean the book lacks",)),
    case("E2-weather", "What is the weather tomorrow?", [None], "not_documented", excludes=(r"does not mean the book lacks",)),
    case("E2-domain-unknown", "Can you tell me about Wau Kikik's waterproofing?", [None], "clarification", excludes=(r"place-specific",)),
    case("E3-origin", "Where does Wau Kikik come from?", "origin_place", "not_documented", edges=("E006",), contains=(r"origin", r"Melaka", r"2002")),
]


def run_case(engine, specification):
    state, setup_replies = {}, []
    for question in specification["setup"]:
        response = engine.respond(question, copy.deepcopy(state))
        setup_replies.append(response)
        state = response["state"]
    response = engine.respond(specification["question"], copy.deepcopy(state))
    errors = []
    if response["status"] != specification["expected_status"]:
        errors.append("Evidence status does not match the requested relation.")
    if response["routing"].get("selected_profile") not in specification["acceptable_profiles"]:
        errors.append("Selected response profile is not an accepted answer to the question.")
    if not set(specification["required_edge_ids"]) <= set(response["edge_ids"]):
        errors.append("Required source edge is missing.")
    for pattern in specification["required_text_patterns"]:
        if not re.search(pattern, response["text"], re.I):
            errors.append("Required answer boundary is absent: " + pattern)
    for pattern in specification["forbidden_text_patterns"]:
        if re.search(pattern, response["text"], re.I):
            errors.append("Inapplicable answer wording is present: " + pattern)
    if response["status"] in {"supported", "explicit_negative", "source_variance"} and not response["source_cards"]:
        errors.append("A substantive supported answer has no source card.")
    for card in response["source_cards"]:
        for edge_id in card["edge_ids"]:
            if edge_id not in response["edge_ids"] or not any(
                all(evidence.get(key) == card[key] for key in ("source_id", "page", "language", "quote"))
                for evidence in engine.edges[edge_id]["evidence"]
            ):
                errors.append("Source card does not match the selected source evidence.")
    if specification["case_id"].startswith("D10-"):
        if setup_replies[-1]["status"] != "explicit_negative":
            errors.append("The exclusion follow-up did not begin with explicit negative evidence.")
        if set(response["edge_ids"]) != set(setup_replies[-1]["edge_ids"]):
            errors.append("An exclusion reason follow-up did not preserve its evidence scope.")
    return {"case_id": specification["case_id"], "question": specification["question"],
            "setup": specification["setup"], "response": response, "failures": errors,
            "passed": not errors}


class FixListAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = WauTraceEngine()

    def test_requested_relations_and_scope_boundaries(self):
        for specification in CASES:
            with self.subTest(case_id=specification["case_id"], question=specification["question"]):
                result = run_case(self.engine, specification)
                self.assertEqual(result["failures"], [], result)

    def test_pending_form_question_expires_on_new_topic(self):
        state = self.engine.respond("Does Wau Kikik have a tail?")["state"]
        answer = self.engine.respond("When was Wau Kikik first used?", state)
        self.assertEqual(answer["status"], "not_documented")
        self.assertNotIn("pending_clarification", answer["state"])
        answer = self.engine.respond("Second form", answer["state"])
        self.assertEqual(answer["routing"].get("selected_profile"), "form_2")
        self.assertEqual(answer["status"], "source_variance")

    def test_why_after_a_new_topic_does_not_reuse_an_old_exclusion(self):
        state = self.engine.respond("Does Wau Kikik have a hummer?")["state"]
        response = self.engine.respond("How many people launch Wau Laga?", state)
        answer = self.engine.respond("Why?", response["state"])
        self.assertNotEqual(answer["routing"].get("selected_profile"), "exclusion_reason")
        self.assertNotIn("E007", answer["edge_ids"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
