"""Development conversation acceptance checks for a bounded cultural guide.

The supplied dialogue and contrast examples are exposed development material,
not an independent or unseen RQ2 evaluation. Assertions check the requested
relation, evidence boundary and conversation state rather than answer snapshots.
"""
from __future__ import annotations

import unittest

from wautrace_engine import WauTraceEngine


# The complete supplied dialogue, preserving its wording and ordering.
TRANSCRIPT = [
    ("What other names does Wau Kikik have?", "aliases", "supported"),
    ("Why is it called Wau Kaca?", "kaca_reason", "supported"),
    ("is this the most famous wau in kuala lampour ?", "place_unknown", "not_documented"),
    ("does it have tail?", None, "clarification"),
    ("First form", "form_component_unknown", "not_documented"),
    ("How many people launch Wau Laga?", "launch_people", "supported"),
    ("when did this wau first used ?", "origin", "not_documented"),
    ("how is it steered?", "steer", "supported"),
    ("What is Wau Kikik covered with?", "covering", "supported"),
    ("What happens when a player is attacked?", "defence", "supported"),
    ("Does Wau Kikik have a hummer?", "hummer", "explicit_negative"),
    ("Why is it called Wau Kaca?", "kaca_reason", "supported"),
    ("is it good for people above 30 years old ?", "age_suitability", "not_documented"),
    ("What forms does Wau Kikik have?", "form_overview", "supported"),
    ("is it used outside Malaysia?", "place_unknown", "not_documented"),
    ("why is it important ?", "importance_overview", "supported"),
    ("How is Wau Kikik related to the Eddy Kite?", "eddy", "supported"),
    ("what is Wou kikik ?", "overview", "supported"),
    ("what is Wau kikik ?", "overview", "supported"),
    ("what is wau at the first place ?", "wau_definition", "supported"),
    ("what is a wau ?", "wau_definition", "supported"),
    ("what is special about wau kikik ?", "overview", "supported"),
    ("What forms does Wau Kikik have?", "form_overview", "supported"),
    ("How many people launch Wau Laga?", "launch_people", "supported"),
    ("Does Wau Kikik have a hummer?", "hummer", "explicit_negative"),
    ("Why is it called Wau Kaca?", "kaca_reason", "supported"),
    ("how many forms does it have ?", "form_count", "supported"),
    ("what are these forms ?", "form_overview", "supported"),
    ("why does it have 3 forms ?", "form_reason", "not_documented"),
    ("which form is more popular ?", "form_comparison_unknown", "not_documented"),
    ("what other names does wau kikik has ?", "aliases", "supported"),
    ("which form is more important ?", "form_comparison_unknown", "not_documented"),
]


class ConversationAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = WauTraceEngine()

    def conversation(self, questions):
        state, replies = {}, []
        for question in questions:
            answer = self.engine.respond(question, state)
            state = answer["state"]
            replies.append(answer)
        return replies

    def assert_route(self, reply, profile, status):
        self.assertEqual(reply["status"], status, reply["text"])
        self.assertEqual(reply["routing"].get("selected_profile"), profile, reply["text"])
        self.assertTrue(reply["text"].strip())

    def assert_exact_sources(self, reply):
        if reply["status"] in {"supported", "explicit_negative", "source_variance"}:
            self.assertTrue(reply["source_cards"], reply["text"])
        for card in reply["source_cards"]:
            self.assertNotRegex(card["scope"], r"\bS\d+:")
            for edge_id in card["edge_ids"]:
                self.assertIn(edge_id, reply["edge_ids"])
                self.assertTrue(any(
                    all(quote.get(key) == card[key] for key in ("source_id", "page", "language", "quote"))
                    for quote in self.engine.edges[edge_id]["evidence"]
                ), (edge_id, card))

    def test_complete_supplied_conversation(self):
        self.assertEqual(len(TRANSCRIPT), 32)
        replies = self.conversation([question for question, _, _ in TRANSCRIPT])
        for number, ((question, profile, status), reply) in enumerate(zip(TRANSCRIPT, replies), 1):
            with self.subTest(turn=number, question=question):
                self.assert_route(reply, profile, status)
                self.assert_exact_sources(reply)

    def test_time_questions_do_not_become_launch_ordinals(self):
        contexts = [[], ["How many people launch Wau Laga?"], ["How many forms does Wau Kikik have?"]]
        questions = ["When was Wau Laga first used?", "When did people start using Wau Kikik?", "When was Wau Kikik introduced?"]
        for context in contexts:
            for question in questions:
                with self.subTest(context=context, question=question):
                    reply = self.conversation(context + [question])[-1]
                    self.assert_route(reply, "origin", "not_documented")
                    self.assertRegex(reply["text"].lower(), r"first.{0,15}us|introduc|start.{0,15}us")

    def test_age_suitability_is_distinct_from_the_kites_age(self):
        for question in ["Can people over 40 play Wau Laga?", "Is Wau Kikik suitable for adults?", "Is this activity suitable for children?"]:
            with self.subTest(question=question):
                reply = self.conversation(["What is Wau Kikik?", question])[-1]
                self.assert_route(reply, "age_suitability", "not_documented")
                self.assertRegex(reply["text"].lower(), r"age|suitab|adult|child")
                self.assertNotIn("inventor", reply["text"].lower())
        reply = self.engine.respond("How old is Wau Kikik?")
        self.assert_route(reply, "origin", "not_documented")

    def test_importance_does_not_supply_an_unasked_attack_fact(self):
        reply = self.conversation(["What is Wau Kikik?", "Why is it important?"])[-1]
        self.assert_route(reply, "importance_overview", "supported")
        self.assertIn("E027", reply["edge_ids"])
        self.assertRegex(reply["text"].lower(), r"reason|explain")
        reply = self.engine.respond("Why is Wau Kikik culturally important?")
        self.assert_route(reply, "cultural_significance", "not_documented")
        self.assertNotIn("speed is most crucial", reply["text"].lower())
        self.assertEqual(self.engine.respond("Which factor matters most when attacking?")["routing"].get("selected_profile"), "attack_speed")

    def test_form_clarification_retains_the_requested_component(self):
        for question, choice, expected, status in [
            ("Does Wau Kikik have a tail?", "First form", "form_component_unknown", "not_documented"),
            ("Does Wau Kikik have a tail?", "Second form", "form_tail", "supported"),
            ("Does Wau Kikik have a head?", "First form", "form_head", "supported"),
            ("Does Wau Kikik have a head?", "Third form", "form_component_unknown", "not_documented"),
        ]:
            with self.subTest(question=question, choice=choice):
                first, reply = self.conversation([question, choice])
                self.assertEqual(first["status"], "clarification")
                self.assert_route(reply, expected, status)
        replies = self.conversation(["Does Wau Kikik have a tail?", "When was Wau Kikik first used?", "Second form"])
        self.assert_route(replies[-1], "form_2", "source_variance")

    def test_definition_scope_and_bounded_spelling(self):
        for question in ["What is a wau?", "What is wau at the first place?", "What does wau mean?"]:
            with self.subTest(question=question):
                reply = self.conversation(["How is Wau Laga controlled?", question])[-1]
                self.assert_route(reply, "wau_definition", "supported")
                self.assertIn("kite", reply["text"].lower())
                self.assert_exact_sources(reply)
        reply = self.engine.respond("What is Wou Kikik?")
        self.assert_route(reply, "overview", "supported")
        # A generic class definition does not authorize a Kikik-only exclusion.
        reply = self.conversation(["What is a wau?", "Does it have a hummer?"])[-1]
        self.assertIn(reply["status"], {"clarification", "not_documented"})
        self.assertNotEqual(reply["routing"].get("selected_profile"), "hummer")
        for followup in ["Why does it have three forms?", "Which form is more popular?"]:
            with self.subTest(followup=followup):
                reply = self.conversation(["What is a wau?", followup])[-1]
                self.assertEqual(reply["status"], "clarification")
                self.assertNotIn(reply["routing"].get("selected_profile"), {"form_reason", "form_comparison_unknown"})
        reply = self.conversation(["What is a wau?", "What makes it special?", "Wau Kikik"])[-1]
        self.assert_route(reply, "overview", "supported")

    def test_forms_description_cause_and_rank_are_distinct(self):
        for question, profile in [
            ("Why are there three forms of Wau Kikik?", "form_reason"),
            ("Why does Wau Kikik have different shapes?", "form_reason"),
            ("Which Wau Kikik type is the most popular?", "form_comparison_unknown"),
            ("Which of the three forms is more important?", "form_comparison_unknown"),
        ]:
            with self.subTest(question=question):
                reply = self.engine.respond(question)
                self.assert_route(reply, profile, "not_documented")
                self.assertNotEqual(reply["intent"], "place_status")
        count, overview = self.conversation(["How many forms does Wau Kikik have?", "What are these forms?"])
        self.assert_route(count, "form_count", "supported")
        self.assert_route(overview, "form_overview", "supported")
        for reply in [count, overview]:
            labels = {label.casefold().strip() for label in reply["suggestions"]}
            self.assertTrue({"first form", "second form", "third form"} <= labels)

    def test_distinctive_summary_preserves_source_characterization(self):
        for question in ["What is special about Wau Kikik?", "What makes Wau Kikik distinctive?"]:
            with self.subTest(question=question):
                reply = self.engine.respond(question)
                self.assert_route(reply, "overview", "supported")
                self.assert_exact_sources(reply)
                text = reply["text"].lower()
                self.assertIn("simplest", text)
                self.assertIn("E027", reply["edge_ids"])
                self.assertNotIn("completely silent", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
