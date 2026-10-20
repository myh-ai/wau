"""Development checks for linguistic routing, source scope and conversation.

These examples are available to the developer. Their outcomes are regression
checks and must not be presented as unseen RQ2 accuracy.
"""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from wautrace_engine import WauTraceEngine, normalize
from graph_inference import resolve_feature

ROOT = Path(__file__).resolve().parent

# Contrasts target meaningful failure modes, not exact-answer snapshots.
FACET_CASES = [
    ("Does Kikik belong to traditional Malay wau?", "classification", "supported"),
    ("What category of kite is Kikik?", "classification", "supported"),
    ("Describe Wau Kikik", "overview", "supported"),
    ("What's Kikik constructed from?", "covering", "supported"),
    ("Which material covers Wau Kikik?", "covering", "supported"),
    ("Is there bamboo in Kikik's frame?", "construction_specs", "not_documented"),
    ("What GSM paper does Kikik need?", "paper_weight", "not_documented"),
    ("How many variants of Kikik exist?", "form_count", "supported"),
    ("Describe Kikik's forms", "form_overview", "supported"),
    ("Tell me about type 1 of Wau Kikik", "form_1", "supported"),
    ("What shape is form number two?", "form_2", "source_variance"),
    ("Does the second form have a tail?", "form_tail", "supported"),
    ("Does the first form have a tail?", "form_component_unknown", "not_documented"),
    ("What's the 3rd form like?", "form_3", "source_variance"),
    ("Who first created Wau Kikik?", "origin", "not_documented"),
    ("What year was Kikik first made?", "origin", "not_documented"),
    ("Does Wau Kikik carry a busur?", "hummer", "explicit_negative"),
    ("Does Kikik use sobek decoration?", "sobek", "explicit_negative"),
    ("Is Wau Kikik silent?", "silence", "not_documented"),
    ("Is Wau Kikik wingless?", "global_wings", "not_documented"),
    ("Does Wau Kikik have leaf shaped wings?", "wings", "explicit_negative"),
    ("Do most traditional Malay wau have leaf shaped wings?", "class_wings", "supported"),
    ("Is Wau Kikik completely undecorated?", "plain", "not_documented"),
    ("Why was it named Wau Kaca?", "kaca_reason", "supported"),
    ("Is the body of Wau Kaca glass?", "kaca_body", "supported"),
    ("What is the glass coating's purpose?", "kaca_reason", "supported"),
    ("How is glass coating mixed?", "glass_recipe", "not_documented"),
    ("Does every Wau Kaca use glass string?", "glass_universal", "not_documented"),
    ("Is glass string still used by Wau Kaca?", "glass_current", "not_documented"),
    ("What do Wau Laga strings usually use?", "laga_glass", "supported"),
    ("Do all Wau Laga strings use glass?", "laga_glass_universal", "not_documented"),
    ("Are Kikik and Laga equivalent names everywhere?", "laga_names", "supported"),
    ("Is Kemetek a documented alias of Kikik?", "kemetek", "not_documented"),
    ("Are Eddy and Kikik the same?", "eddy", "supported"),
    ("Which state recognises Kikik as its official wau?", "official", "supported"),
    ("Is Kikik still officially associated with Melaka?", "official_current", "not_documented"),
    ("Where was playing Wau Laga popular?", "popularity", "supported"),
    ("How many players help fly Wau Laga?", "launch_people", "supported"),
    ("Do I need a partner to launch Laga?", "launch_people", "supported"),
    ("Who helps raise Wau Laga?", "launch_people", "supported"),
    ("Explain juru main tali", "launch_people", "supported"),
    ("What does the puller do?", "launch_signal", "supported"),
    ("How far apart should the players stand?", "launch_distance", "supported"),
    ("How far do the launcher and puller stand from one another?", "launch_distance", "supported"),
    ("Where is the rolled kite string placed?", "launch_ground", "supported"),
    ("What is the Wau Laga launch procedure?", "launch_process", "supported"),
    ("How high does Wau Laga fly in the book?", "height", "supported"),
    ("Why does Wau Laga spin near a player?", "wind", "supported"),
    ("How can I steady Wau Laga?", "stability", "supported"),
    ("My Wau Laga is diving; what does the book describe?", "dive", "supported"),
    ("How do I point the head of Wau Laga?", "steer", "supported"),
    ("What does the book say about defending against an opponent?", "defence", "supported"),
    ("My opponent attacks my kite; what should I do?", "defence", "supported"),
    ("How do I attack the rival kite?", "attack", "supported"),
    ("Which factor matters most when attacking?", "attack_speed", "supported"),
    ("Is there an advantage to flying underneath a rival?", "attack_position", "source_variance"),
    ("What skills are required for Wau Laga?", "skill", "supported"),
    ("Does Wau Laga play require fast reactions?", "skill", "supported"),
    ("Can I legally fly Wau Laga here today?", "legal", "not_documented"),
    ("Does the 200 foot height allow legal flight?", "legal_height", "not_documented"),
]


class EngineDevelopmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = WauTraceEngine()

    def conversation(self, questions):
        state, responses = {}, []
        for question in questions:
            answer = self.engine.respond(question, state)
            state = answer["state"]
            responses.append(answer)
        return responses

    def test_development_facet_matrix(self):
        for question, facet, status in FACET_CASES:
            with self.subTest(question=question):
                result = self.engine.respond(question)
                self.assertEqual(result["routing"].get("selected_profile"), facet, result["text"])
                self.assertEqual(result["status"], status)

    def test_surface_normalization_preserves_real_words(self):
        self.assertIn("strong wind", normalize("strong winds"))
        self.assertIn("kite dive", normalize("kites diving"))
        self.assertIn("what is", normalize("What's"))
        self.assertIn("attack", normalize("attacks"))
        self.assertIn("kemetek", normalize("Kemetek"))

    def test_typo_correction_is_generic_and_auditable(self):
        for word, normalized in [("kacha", "kaca"), ("kikikk", "kikik"), ("melakka", "melaka")]:
            with self.subTest(word=word):
                self.assertEqual(normalize(word), normalized)
                result = self.engine.respond(f"What is {word}?")
                self.assertTrue(result["routing"]["normalizations"])
        self.assertEqual(self.engine.respond("Does Wau Kikikk have a busur?")["routing"]["selected_profile"], "hummer")
        self.assertEqual(self.engine.respond("Why is it named Wau Kacha?")["routing"]["selected_profile"], "kaca_reason")
        self.assertEqual(self.engine.respond("What is Kemetek?")["status"], "not_documented")

    def test_unrelated_controls_do_not_receive_cultural_answers(self):
        for question in ["What is a paper airplane made from?", "How do I control my blood pressure?",
                         "What are Saturn's rings made of?", "Which state is my tax return in?",
                         "Who first built the telephone?", "How many people play football?"]:
            with self.subTest(question=question):
                result = self.engine.respond(question)
                self.assertIn(result["status"], {"not_documented", "clarification"})
                self.assertEqual(result["edge_ids"], [])

    def test_unrecognized_attribute_does_not_become_overview(self):
        for question in ["Is Wau Kikik waterproof?", "Is Wau Kikik portable?"]:
            result = self.engine.respond(question)
            self.assertEqual(result["status"], "clarification")
            self.assertEqual(result["edge_ids"], [])

    def test_clarification_choice_precedes_domain_gate(self):
        a, b = self.conversation(["Laga?", "the name"])
        self.assertEqual(a["status"], "clarification")
        self.assertEqual(b["routing"]["selected_profile"], "laga_names")
        a, b = self.conversation(["Explain Laga", "the playing practice"])
        self.assertEqual(b["intent"], "practice_context")

    def test_form_followup_and_scope(self):
        results = self.conversation(["How many forms does Kikik have?", "And the second?", "Does it have a tail?", "Is one page wrong?"])
        self.assertEqual([r["status"] for r in results], ["supported", "source_variance", "supported", "source_variance"])
        self.assertEqual(results[2]["routing"]["selected_profile"], "form_tail")

    def test_form_clarification_preserves_the_requested_component(self):
        for component, selected_form in [("tail", "First"), ("head", "Second"), ("tail", "Third")]:
            with self.subTest(component=component, selected_form=selected_form):
                replies = self.conversation(["What is Wau Kikik?", f"Does it have a {component}?", f"{selected_form} form"])
                result = replies[-1]
                self.assertEqual(replies[-2]["status"], "clarification")
                self.assertEqual(result["routing"].get("selected_profile"), "form_component_unknown")
                self.assertIn(f"{selected_form.lower()} form has a {component}", result["text"])
                self.assertEqual(result["status"], "not_documented")
                self.assertFalse(result["source_cards"])
                self.assertNotIn("requested_component", result["state"])

    def test_form_collection_request_clears_specific_form_selection(self):
        for collection, expected in [("How many forms does it have?", "form_count"),
                                     ("What forms does it have?", "form_overview")]:
            with self.subTest(collection=collection):
                replies = self.conversation(["Describe form 1 of Kikik", collection, "Does it have a tail?"])
                self.assertEqual(replies[1]["routing"].get("selected_profile"), expected)
                self.assertNotIn("form_number", replies[1]["state"])
                self.assertEqual(replies[-1]["status"], "clarification")
                self.assertEqual(replies[-1]["state"]["pending_clarification"], "form_number")

    def test_form_reason_and_preference_are_not_descriptive_facts(self):
        for question, expected in [("And why?", "form_reason"), ("Which type is best?", "form_comparison_unknown")]:
            with self.subTest(question=question):
                result = self.conversation(["What forms does Wau Kikik have?", question])[-1]
                self.assertEqual(result["routing"].get("selected_profile"), expected)
                self.assertEqual(result["status"], "not_documented")
                if expected == "form_reason":
                    self.assertTrue(all(card["quote"] == "It consists of three different types." for card in result["source_cards"]))
                else:
                    self.assertIn("E016", result["edge_ids"])

    def test_source_gap_keeps_absence_of_citation(self):
        a, b = self.conversation(["Is Kemetek the same as Kikik?", "Which page supports that?"])
        self.assertEqual(b["status"], "not_documented")
        self.assertEqual(b["source_cards"], [])

    def test_naming_to_current_string_followup(self):
        a, b = self.conversation(["Why is it called Wau Kaca?", "Do all of them still use it?"])
        self.assertEqual(b["status"], "not_documented")
        self.assertIn("2002", b["text"])

    def test_kinds_of_material_are_not_numbered_kite_forms(self):
        for noun in ["string", "line", "kite string"]:
            with self.subTest(noun=noun):
                result = self.conversation(["Why is it called Wau Kaca?", f"Do all of them still use that kind of {noun} today?"])[-1]
                self.assertEqual(result["routing"].get("selected_profile"), "glass_current")
                self.assertEqual(result["status"], "not_documented")
                self.assertNotIn("forms", result["routing"]["concepts"])
        for noun in ["kinds", "sorts", "varieties"]:
            result = self.engine.respond(f"How many {noun} of Wau Kikik exist?")
            self.assertEqual(result["routing"].get("selected_profile"), "form_count")
            self.assertEqual(result["status"], "supported")

    def test_distance_does_not_become_height(self):
        a, b = self.conversation(["How far apart do Laga players stand?", "Is that also its height?"])
        self.assertEqual(b["routing"]["selected_profile"], "height_separation")
        self.assertIn("different measurements", b["text"])

    def test_entity_switch_does_not_inherit_feature_negation(self):
        a, b = self.conversation(["Does Kikik have a busur?", "What about Wau Laga?"])
        self.assertEqual(b["status"], "not_documented")
        self.assertEqual(b["routing"]["selected_profile"], "laga_features")

    def test_defender_attacker_contrast(self):
        results = self.conversation(["The other kite is attacking mine. What does the book say?", "And the attacker?"])
        self.assertEqual(results[0]["intent"], "defence")
        self.assertEqual(results[1]["intent"], "attack")

    def test_age_threshold_and_attack_position_are_distinct(self):
        for question in ["What should a player do when their Wau Laga is under attack?",
                         "What should a player under attack do?", "My kite is under attack; how should I respond?"]:
            with self.subTest(question=question):
                result = self.engine.respond(question)
                self.assertNotIn("age_suitability", self.engine.router.analyze(question)["concepts"])
                self.assertEqual(result["routing"].get("selected_profile"), "defence")
                self.assertEqual(result["status"], "supported")
                self.assertTrue(result["source_cards"])
                self.assertTrue(all(card["page"] == 148 for card in result["source_cards"]))
        for question in ["Can players under 30 play Wau Laga?", "Is it suitable for people under 30 years old?",
                         "Can people over forty play Wau Laga?"]:
            with self.subTest(question=question):
                result = self.engine.respond(question)
                self.assertEqual(result["routing"].get("selected_profile"), "age_suitability")
                self.assertEqual(result["status"], "not_documented")
                self.assertFalse(result["source_cards"])

    def test_nickname_social_and_reset(self):
        results = self.conversation(["My name is Sara", "Hi there", "What is Kikik made of?", "Thanks for your help", "Bye for now", "reset", "What is my name?"])
        self.assertEqual(results[0]["state"]["nickname"], "Sara")
        self.assertIn("Sara", results[1]["text"])
        self.assertIn("Sara", results[2]["text"])
        self.assertEqual(results[3]["status"], "system")
        self.assertTrue(results[5]["reset"])
        self.assertNotIn("nickname", results[6]["state"])

    def test_non_names_are_not_stored(self):
        for utterance in ["I'm confused", "I am flying a kite", "I am not sure"]:
            self.assertNotIn("nickname", self.engine.respond(utterance)["state"])

    def test_social_clock_uses_supplied_local_hour(self):
        self.assertIn("Good evening", self.engine.respond("Hi there", {"local_hour":20})["text"])
        self.assertIn("Good morning", self.engine.respond("Hello", {"local_hour":8})["text"])

    def test_suggestions_exclude_current_intent(self):
        response = self.engine.respond("How is Wau Laga steered?")
        self.assertNotIn("How is Wau Laga steered?", response["suggestions"])

    def test_every_source_card_is_exact_and_clean(self):
        for question, _, _ in FACET_CASES:
            response = self.engine.respond(question)
            for card in response["source_cards"]:
                self.assertNotRegex(card["scope"], r"\bS\d+:")
                self.assertTrue(any(any(all(quote.get(k) == card[k] for k in ("source_id", "page", "language", "quote")) for quote in edge["evidence"]) for edge in self.engine.edges.values()))

    def test_edge_approval_does_not_approve_response_composition(self):
        response = self.engine.respond("What is Kikik covered with?")
        self.assertEqual(response["author_review_status"], "approved")
        self.assertEqual(response["review_status"], "source_checked_representation_pending")

    def test_review_approval_is_bound_to_exact_claim_content(self):
        review = json.loads((ROOT / "reviews" / "operational_claim_review.json").read_text())
        immutable = copy.deepcopy(self.engine.network["edges"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.json"
            path.write_text(json.dumps(review))
            engine = WauTraceEngine(review_path=path)
            self.assertEqual(len(engine.approved_edge_ids), 74)
            self.assertEqual(engine.network["edges"], immutable)
            review["claims"][0]["answer_en"] += " altered"
            path.write_text(json.dumps(review))
            self.assertFalse(WauTraceEngine(review_path=path).approved_edge_ids)
            self.assertFalse(WauTraceEngine(review_path=Path(directory) / "missing.json").approved_edge_ids)

    def test_time_questions_do_not_swallow_procedural_when(self):
        for question in ["When should I lock the line?", "When do you lock the string?", "When is the string locked?"]:
            with self.subTest(question=question):
                result = self.engine.respond(question)
                self.assertEqual(result["routing"].get("selected_profile"), "steer")
                self.assertEqual(result["status"], "supported")
        for question in ["Since when has Wau Kikik been flown?", "What year was Wau Kikik invented?", "How old is Wau Kikik?"]:
            self.assertEqual(self.engine.respond(question)["routing"].get("selected_profile"), "origin")

    def test_appearance_and_named_comparison_are_different_relations(self):
        for question in ["What does Wau Kikik look like?", "Describe Wau Kikik's appearance"]:
            self.assertEqual(self.engine.respond(question)["routing"].get("selected_profile"), "form_overview")
        for question in ["Which western kite looks like Wau Kikik?", "What is the Malay Kite?"]:
            self.assertEqual(self.engine.respond(question)["routing"].get("selected_profile"), "eddy")
        self.assertEqual(self.engine.respond("What shape is the second form of Wau Kikik?")["routing"].get("selected_profile"), "form_2")

    def test_exclusion_reason_reuses_only_the_last_negative_evidence(self):
        for feature in ["hummer", "sobek carvings", "leaf-shaped wings"]:
            first, followup = self.conversation([f"Does Wau Kikik have {feature}?", "Why not?"])
            self.assertEqual(followup["status"], "not_documented")
            self.assertEqual(followup["routing"].get("selected_profile"), "exclusion_reason")
            self.assertEqual(set(followup["edge_ids"]), set(first["edge_ids"]))
        result = self.conversation(["Does Kikik have a hummer?", "What is Wau Kikik covered with?", "Why?"])[-1]
        self.assertNotEqual(result["routing"].get("selected_profile"), "exclusion_reason")

    def test_rejected_assertion_cannot_enter_retrieval(self):
        network = copy.deepcopy(self.engine.network)
        relevant = next(edge for edge in network["edges"] if edge["relation"] == "has_covering_material")
        relevant["author_decision"] = "rejected"
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/"network.json"
            path.write_text(json.dumps(network))
            with self.assertRaisesRegex(ValueError, "unresolved source selector"):
                WauTraceEngine(path)

    def test_majority_does_not_create_subtype_fact(self):
        known = resolve_feature(self.engine.network, "wau_kikik", "leaf_shaped_wings")
        missing = resolve_feature(self.engine.network, "wau_laga_named_type", "leaf_shaped_wings")
        self.assertFalse(known["value"])
        self.assertFalse(missing["inherited_as_subtype_fact"])
        self.assertIsNone(missing["value"])

    def test_runtime_executes_graph_feature_priority(self):
        answer = self.engine.respond("Does Wau Kikik have leaf-shaped wings?")
        trace = answer["routing"]["graph_inference"]
        self.assertEqual(trace["status"], "explicit_negative")
        self.assertFalse(trace["value"])
        self.assertTrue(trace["class_context_edge_ids"])
        self.assertFalse(trace["inherited_as_subtype_fact"])
        self.assertEqual(trace["class_candidate_action"], "overridden_for_subtype_answer")

    def test_launch_preparation_is_not_repeated(self):
        response = self.engine.respond("What is the Wau Laga launch procedure?")
        self.assertEqual(response["text"].lower().count("tangling"), 1)

    def test_role_labels_do_not_create_four_players(self):
        response = self.engine.respond("What is juru anjong?")
        self.assertIn("two players", response["text"].lower())
        self.assertIn("does not explicitly map", response["text"])

    def test_ordinal_followups_preserve_the_discussion_topic(self):
        for launch in ["How do I launch Wau Laga?", "Who is needed to launch Wau Laga?"]:
            for followup in ["What does the second person do?", "What does the other player do?", "And the second?", "What does the first participant do?"]:
                with self.subTest(launch=launch, followup=followup):
                    _, result = self.conversation([launch, followup])
                    self.assertEqual(result["routing"].get("selected_profile"), "launch_roles")
                    self.assertEqual(result["status"], "supported")
                    self.assertIn("puller", result["text"])
                    self.assertIn("launcher", result["text"])
                    self.assertTrue(all(card["page"] == 144 for card in result["source_cards"]))
        for followup in ["What does the second person do?", "What does the third player do?"]:
            _, result = self.conversation(["What forms does Wau Kikik have?", followup])
            self.assertNotEqual(result["intent"], "forms")
        _, result = self.conversation(["How do I launch Wau Laga?", "What is the second form of Wau Kikik like?"])
        self.assertEqual(result["routing"]["selected_profile"], "form_2")
        self.assertEqual(self.engine.respond("Does the second Kikik have a tail?")["routing"].get("selected_profile"), "form_tail")
        self.assertEqual(self.engine.respond("How many designs does Kikik come in?")["routing"].get("selected_profile"), "form_count")

    def test_unsupported_places_do_not_receive_other_geographic_claims(self):
        for place in ["Kelantan", "Johor", "Kuala Lumpur", "London", "a village near me"]:
            for question in [f"Is Wau Laga played in {place}?", f"Is Wau Kikik the state kite of {place}?"]:
                with self.subTest(question=question):
                    result = self.engine.respond(question)
                    self.assertEqual(result["status"], "not_documented")
                    self.assertEqual(result["routing"]["selected_profile"], "place_unknown")
                    self.assertFalse(result["source_cards"])
        for question in ["Is Wau Kikik from Melaka?", "Is Wau Kikik Kelantan's official kite?", "Where does Wau Kikik come from?", "Is Wau Laga only played on the west coast of Peninsular Malaysia?", "Is Wau Laga popular in Peninsular Malaysia?"]:
            with self.subTest(question=question):
                self.assertEqual(self.engine.respond(question)["status"], "not_documented")

    def test_documented_places_keep_the_relation_and_time_scope(self):
        for question, profile in [
                ("Is Wau Kikik the official kite of Malacca?", "official"),
                ("Which state has Wau Kikik as its official kite?", "official"),
                ("Is Wau Kikik Melaka's official kite?", "official"),
                ("Where was playing Wau Laga popular?", "popularity"),
                ("Is Wau Laga popular on the west coast of Peninsular Malaysia?", "popularity")]:
            with self.subTest(question=question):
                result = self.engine.respond(question)
                self.assertEqual(result["routing"].get("selected_profile"), profile)
                self.assertEqual(result["status"], "supported")
                self.assertIn("2002", result["text"])
        for question in ["Is Wau Kikik still official in Melaka?", "Is Wau Laga popular on the west coast of Peninsular Malaysia today?"]:
            self.assertEqual(self.engine.respond(question)["status"], "not_documented")

    def test_hummer_sound_and_absolute_silence_are_distinct(self):
        for question in ["Does Wau Kikik make a humming sound?", "Does Wau Kikik hum?", "Is there humming from Wau Kikik?", "Does Wau Kikik have a hummer?"]:
            with self.subTest(question=question):
                result = self.engine.respond(question)
                self.assertEqual(result["routing"].get("selected_profile"), "hummer")
                self.assertEqual(result["status"], "explicit_negative")
                self.assertIn("does not establish", result["text"])
        for question in ["Does Wau Kikik make any sound?", "Is Wau Kikik completely silent?", "Does having no hummer mean it makes no sound at all?"]:
            with self.subTest(question=question):
                result = self.engine.respond(question)
                self.assertEqual(result["status"], "not_documented")

    def test_form_overview_and_specific_shape_have_scoped_badges(self):
        for question in ["What forms does Wau Kikik have?", "Describe Kikik's forms", "How many types of Wau Kikik exist?"]:
            with self.subTest(question=question):
                result = self.engine.respond(question)
                self.assertEqual(result["status"], "supported")
                self.assertFalse(any(self.engine.edges[eid]["status"] == "source_variance" for eid in result["edge_ids"]))
        for question in ["What shape is form 2?", "Is the third form square or rectangular?"]:
            self.assertEqual(self.engine.respond(question)["status"], "source_variance")

    def test_help_and_commerce_are_not_cultural_facts(self):
        for question in ["What can you do?", "What topics can I ask about?", "Can you help me?", "How can you help me?", "Help"]:
            with self.subTest(question=question):
                result = self.engine.respond(question)
                self.assertEqual(result["status"], "system")
                self.assertIn("Wau Kikik", result["text"])
                self.assertFalse(result["source_cards"])
        for question in ["Where can I buy Wau Kikik?", "What does Wau Kikik cost?", "Any shops selling Wau Laga?", "What's the price of Wau Kikik?", "Can I purchase a kite in Melaka?"]:
            with self.subTest(question=question):
                result = self.engine.respond(question)
                self.assertEqual(result["status"], "not_documented")
                self.assertIn("outside", result["text"])
                self.assertFalse(result["source_cards"])

    def test_role_actions_and_launch_procedure_use_separate_facets(self):
        for question in ["What does a puller do?", "What is the launcher's job?", "Explain the role of the launcher", "What is the responsibility of juru tarik?"]:
            with self.subTest(question=question):
                result = self.engine.respond(question)
                self.assertEqual(result["routing"].get("selected_profile"), "launch_signal")
                self.assertIn("signal", result["text"])
        for question in ["How do I launch Wau Laga?", "How can I launch a Wau Laga?", "Describe the Wau Laga launch process"]:
            self.assertEqual(self.engine.respond(question)["routing"].get("selected_profile"), "launch_process")
        self.assertEqual(self.engine.respond("Does Wau Laga have a head?")["status"], "not_documented")

    def test_documented_parts_do_not_support_undocumented_colours(self):
        for question in ["Is Wau Kikik red?", "Does Wau Kikik use blue paper?", "What colour is the head of the first form?", "Is the tail of Wau Kikik green?"]:
            with self.subTest(question=question):
                result = self.engine.respond(question)
                self.assertEqual(result["routing"].get("selected_profile"), "colour_unknown")
                self.assertEqual(result["status"], "not_documented")
                self.assertFalse(result["source_cards"])
        self.assertEqual(self.engine.respond("Does the first form of Kikik have a head?")["status"], "supported")
        self.assertEqual(self.engine.respond("What is Wau Kikik covered with?")["status"], "supported")

    def test_non_spatial_prepositional_phrases_do_not_become_places(self):
        for phrase in ["at all", "in all", "in general", "at launch", "in competition", "at low altitude", "at once", "on its own", "at the start", "in English", "in the book", "in total"]:
            with self.subTest(phrase=phrase):
                analysis = self.engine.router.analyze("Does Wau Kikik have wings " + phrase + "?")
                self.assertFalse(self.engine._location_request(analysis)["places"])
        _, answer = self.conversation(["Does Wau Kikik have leaf-shaped wings?", "Does that mean it has no wings at all?"])
        self.assertEqual(answer["routing"].get("selected_profile"), "global_wings")
        self.assertEqual(answer["status"], "not_documented")
        for phrase in ["in Kelantan", "at Kuala Lumpur", "from Johor"]:
            self.assertTrue(self.engine._location_request(self.engine.router.analyze("Is Wau Laga played " + phrase + "?"))["places"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
