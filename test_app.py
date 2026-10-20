"""Interface checks; these do not replace the research conversation evaluation."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest

from app import clean_nickname, local_clock, time_greeting, resolve_clock, prepare_response, response_csv, load_study_config

APP = Path(__file__).with_name("app.py")


class GreetingChecks(unittest.TestCase):
    def test_hour_boundaries(self):
        for hour, phrase in [(0, "Good evening."), (4, "Good evening."), (5, "Good morning."), (11, "Good morning."), (12, "Good afternoon."), (17, "Good afternoon."), (18, "Good evening."), (23, "Good evening.")]:
            with self.subTest(hour=hour):
                self.assertEqual(time_greeting(hour), phrase)
        self.assertEqual(time_greeting(9, "Sam"), "Good morning, Sam.")

    def test_timezone_conversion_and_fallback(self):
        reference = datetime(2026, 10, 18, 22, 30, tzinfo=timezone.utc)
        result, fallback = local_clock("Asia/Qatar", reference)
        self.assertEqual((result.day, result.hour), (19, 1))
        self.assertFalse(fallback)
        result, fallback = local_clock("Unavailable/Zone", reference)
        self.assertEqual((result.day, result.hour), (18, 22))
        self.assertTrue(fallback)

    def test_browser_timezone_and_offset_precede_utc_fallback(self):
        reference = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
        clock, zone, source = resolve_clock("Automatic (browser)", "Asia/Kuala_Lumpur", -480, reference)
        self.assertEqual((clock.hour, zone, source), (20, "Asia/Kuala_Lumpur", "Browser timezone"))
        self.assertEqual(time_greeting(clock.hour), "Good evening.")
        clock, zone, source = resolve_clock("Automatic (browser)", None, -480, reference)
        self.assertEqual(clock.hour, 20)
        self.assertEqual(source, "Browser UTC offset")
        clock, zone, source = resolve_clock("Automatic (browser)", None, None, reference)
        self.assertEqual((clock.hour, zone), (12, "UTC"))
        self.assertIn("unavailable", source)
        clock, zone, source = resolve_clock("Asia/Qatar", "Asia/Kuala_Lumpur", -480, reference)
        self.assertEqual((clock.hour, zone, source), (15, "Asia/Qatar", "Manual timezone"))

    def test_nickname_is_short_and_single_line(self):
        self.assertEqual(clean_nickname("  Sam\n  Lee  "), "Sam Lee")
        self.assertEqual(len(clean_nickname("A" * 80)), 40)


class InterfaceChecks(unittest.TestCase):
    def start(self):
        app = AppTest.from_file(str(APP), default_timeout=15).run()
        self.assertEqual(len(app.exception), 0)
        return app

    def test_opening_and_topic_menu(self):
        app = self.start()
        self.assertEqual(app.title[0].value, "WauTrace")
        self.assertEqual(len(app.chat_input), 1)
        for key in ["topic_names", "topic_forms", "topic_features", "topic_place", "topic_launching", "topic_control", "topic_competition", "topic_book_limits"]:
            app.button(key=key).click().run()
            self.assertEqual(len(app.exception), 0, key)
        self.assertEqual(len(app.session_state["messages"]), 16)
        self.assertGreater(len(app.expander), 2)

    def test_nickname_survives_questions_and_start_over_clears_it(self):
        app = self.start()
        app.text_input(key="nickname_input").set_value("Sam").run()
        next(button for button in app.button if button.label == "Remember nickname").click().run()
        self.assertEqual(app.session_state["nickname"], "Sam")
        self.assertIn("Sam", app.subheader[0].value)
        app.button(key="topic_names").click().run()
        self.assertEqual(app.session_state["nickname"], "Sam")
        self.assertTrue(app.session_state["messages"])
        next(button for button in app.button if button.label == "Start over").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state["nickname"], "")
        self.assertEqual(app.session_state["messages"], [])
        self.assertEqual(app.session_state["conversation_state"], {})
        self.assertEqual(app.text_input(key="nickname_input").value, "")

    def test_typed_reset_clears_nickname_and_context(self):
        app = self.start()
        app.text_input(key="nickname_input").set_value("Sam").run()
        next(button for button in app.button if button.label == "Remember nickname").click().run()
        app.button(key="topic_names").click().run()
        app.chat_input[0].set_value("reset").run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state["nickname"], "")
        self.assertEqual(app.session_state["messages"], [])
        self.assertEqual(app.session_state["conversation_state"], {})
        self.assertEqual(app.text_input(key="nickname_input").value, "")

    def test_chat_input_and_timezone_selection(self):
        app = self.start()
        app.selectbox(key="selected_zone").select("Asia/Kuala_Lumpur").run()
        self.assertEqual(app.session_state["selected_zone"], "Asia/Kuala_Lumpur")
        app.chat_input[0].set_value("What other names does Wau Kikik have?").run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.session_state["messages"]), 2)
        self.assertTrue(app.session_state["messages"][-1]["text"])

    def test_chat_name_and_social_messages(self):
        app = self.start()
        for message in ["My name is Sara", "Hi there", "Thanks", "Bye"]:
            app.chat_input[0].set_value(message).run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(app.session_state["messages"][-1]["status"], "system")
        self.assertEqual(app.session_state["nickname"], "Sara")
        self.assertIn("Sara", app.subheader[0].value)

    def test_source_details_and_form_choices(self):
        app = self.start()
        app.button(key="topic_names").click().run()
        self.assertTrue(any(item.label == "More detail" for item in app.expander))
        self.assertTrue(any(item.label.startswith("Read the source") for item in app.expander))
        app.button(key="topic_forms").click().run()
        self.assertEqual([app.button(key=f"suggestion_{i}").label for i in range(3)],
                         ["First form", "Second form", "Third form"])
        app.button(key="suggestion_2").click().run()
        self.assertEqual(app.session_state["messages"][-1]["status"], "source_variance")
        self.assertEqual(len(app.exception), 0)

    def test_clarification_button_completes_the_requested_attribute(self):
        app = self.start()
        app.chat_input[0].set_value("Does Wau Kikik have a tail?").run()
        self.assertTrue(any(item.value == "Choose an option:" for item in app.caption))
        app.button(key="suggestion_0").click().run()
        reply = app.session_state["messages"][-1]
        self.assertEqual(reply["routing"].get("selected_profile"), "form_component_unknown")
        self.assertEqual(reply["status"], "not_documented")
        self.assertEqual(len(app.exception), 0)

    def test_external_questionnaire_journey_and_clear(self):
        app = self.start()
        app.button(key="open_study").click().run()
        self.assertEqual(len(app.chat_input), 0)
        app.checkbox(key="study_adult").check()
        app.checkbox(key="study_consent").check()
        app.radio(key="study_familiarity").set_value("I had no prior knowledge of Wau Kikik.")
        next(button for button in app.button if button.label == "Begin tasks").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state["study_stage"], "tasks")
        for index in range(6):
            self.assertEqual(len(app.chat_input), 1)
            app.button(key="study_attempt" if index % 2 == 0 else "study_skip").click().run()
            self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state["study_stage"], "questionnaire")
        self.assertEqual(len(app.radio), 0)
        links = app.get("link_button")
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].proto.url, "https://forms.gle/vHHtfYTKqShZF1zc8")
        self.assertFalse(any(button.label == "Prepare my response" for button in app.button))
        app.button(key="study_external_done").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state["study_stage"], "end")
        self.assertIsNone(app.session_state["study_payload"])
        self.assertEqual(len(app.get("download_button")), 0)
        app.button(key="study_clear").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state["study_stage"], "closed")
        self.assertIsNone(app.session_state["study_payload"])

    def test_consent_and_all_item_validation(self):
        app = self.start()
        app.button(key="open_study").click().run()
        next(button for button in app.button if button.label == "Begin tasks").click().run()
        self.assertEqual(app.session_state["study_stage"], "intro")
        self.assertTrue(app.warning)


class StudyDataChecks(unittest.TestCase):
    def test_preview_is_default_and_no_personal_data_is_exported(self):
        config = load_study_config()
        payload = prepare_response(config, "I had no prior knowledge of Wau Kikik.", [{"task_id": "T1", "status": "attempted", "nickname": "Not exported"}], [3] * 16)
        self.assertTrue(payload["preview_only"])
        self.assertEqual(set(payload), {"instrument", "preview_only", "adult_eligibility_confirmed", "voluntary_participation_confirmed", "q0_prior_familiarity", "task_attempts", "responses"})
        self.assertEqual(payload["task_attempts"], [{"task_id": "T1", "status": "attempted"}])
        self.assertEqual(len(response_csv(payload).splitlines()), 2)
        for invalid in [[3] * 15, [0] * 16, [True] * 16]:
            with self.assertRaises(ValueError):
                prepare_response(config, "I had no prior knowledge of Wau Kikik.", [], invalid)


if __name__ == "__main__":
    unittest.main()
