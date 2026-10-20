"""WauTrace: a small, source-bound cultural education interface."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import csv
from html import escape
import io
import json
import os
from pathlib import Path
import re
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import streamlit as st

from wautrace_engine import WauTraceEngine

BASE = Path(__file__).resolve().parent
TIMEZONES = ("Automatic (browser)", "Asia/Kuala_Lumpur", "Asia/Qatar", "UTC", "Europe/London", "America/New_York")
TOPICS = (
    ("Names", "What other names does Wau Kikik have?"),
    ("Forms", "What forms does Wau Kikik have?"),
    ("Features", "Does Wau Kikik have a hummer?"),
    ("Place", "Which state is Wau Kikik associated with?"),
    ("Launching", "Who launches Wau Laga?"),
    ("Control", "How is Wau Laga controlled?"),
    ("Competition", "What is Wau Laga competition about?"),
    ("Book limits", "What does the book not tell us?"),
)
STATUS_LABELS = {
    "supported": "Documented in the book",
    "explicit_negative": "Explicitly ruled out in the book",
    "source_variance": "The sources differ or need context",
    "not_documented": "Not documented in this collection",
    "clarification": "Let's clarify your question",
    "system": "Conversation help",
}


def time_greeting(hour: int, nickname: str = "") -> str:
    """The same three hour ranges used by Algorithm 1 in the research plan."""
    if not 0 <= hour <= 23:
        raise ValueError("Hour must be between 0 and 23.")
    phrase = "Good morning" if 5 <= hour < 12 else "Good afternoon" if 12 <= hour < 18 else "Good evening"
    return f"{phrase}, {nickname}." if nickname else f"{phrase}."


def local_clock(zone: str, now: datetime | None = None) -> tuple[datetime, bool]:
    """Return an aware clock; an unavailable zone honestly falls back to UTC."""
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError("The reference time must be timezone-aware.")
    try:
        return instant.astimezone(ZoneInfo(zone)), False
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return instant.astimezone(timezone.utc), True


def resolve_clock(selected_zone: str, browser_zone: str | None, browser_offset: int | None = None,
                  now: datetime | None = None) -> tuple[datetime, str, str]:
    """Prefer a manual choice, otherwise the browser zone, offset, then UTC."""
    if selected_zone != TIMEZONES[0]:
        clock, fallback = local_clock(selected_zone, now)
        return clock, "UTC" if fallback else selected_zone, "UTC fallback" if fallback else "Manual timezone"
    if browser_zone:
        clock, fallback = local_clock(browser_zone, now)
        if not fallback:
            return clock, browser_zone, "Browser timezone"
    if isinstance(browser_offset, int) and -840 <= browser_offset <= 840:
        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None:
            raise ValueError("The reference time must be timezone-aware.")
        tz = timezone(-timedelta(minutes=browser_offset))
        return instant.astimezone(tz), str(tz), "Browser UTC offset"
    clock, _ = local_clock("UTC", now)
    return clock, "UTC", "UTC fallback: browser timezone unavailable"


def browser_clock() -> tuple[datetime, str, str]:
    # st.context is read-only. A missing value in AppTest or a browser handshake
    # must not silently select the author's timezone.
    zone = st.context.timezone
    offset = st.context.timezone_offset
    if zone:
        st.session_state.browser_zone = zone
    if offset is not None:
        st.session_state.browser_offset = offset
    return resolve_clock(st.session_state.selected_zone, st.session_state.get("browser_zone"),
                         st.session_state.get("browser_offset"))


def clean_nickname(value: str) -> str:
    """Keep a short, single-line display name; no identity is required."""
    return " ".join(value.split())[:40]


def initialise_session() -> None:
    defaults = {"messages": [], "conversation_state": {}, "nickname": "", "nickname_input": "", "selected_zone": TIMEZONES[0], "last_suggestions": [], "study_stage": "closed", "study_task_index": 0, "study_attempts": [], "study_payload": None}
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    if st.session_state.pop("sync_nickname_input", False):
        st.session_state.nickname_input = st.session_state.nickname


def reset_conversation() -> None:
    st.session_state.messages = []
    st.session_state.conversation_state = {}
    st.session_state.last_suggestions = []
    st.session_state.nickname = ""
    st.session_state.nickname_input = ""


def save_nickname() -> None:
    name = clean_nickname(st.session_state.get("nickname_input", ""))
    st.session_state.nickname = name
    st.session_state.conversation_state["nickname"] = name


@st.cache_resource(show_spinner=False)
def get_engine() -> WauTraceEngine:
    return WauTraceEngine()


def submit_question(question: str) -> None:
    question = question.strip()
    if not question:
        return
    state = dict(st.session_state.conversation_state)
    state["nickname"] = st.session_state.nickname
    state["local_hour"] = st.session_state.get("greeting_hour", browser_clock()[0].hour)
    response = get_engine().respond(question, state=state)
    if response.get("reset"):
        st.session_state.messages = []
        st.session_state.conversation_state = {}
        st.session_state.last_suggestions = []
        st.session_state.nickname = ""
        st.session_state.sync_nickname_input = True
        return
    next_state = response.get("state", state)
    if "nickname" in next_state and next_state["nickname"] != st.session_state.nickname:
        st.session_state.nickname = clean_nickname(str(next_state["nickname"]))
        st.session_state.sync_nickname_input = True
    st.session_state.messages.extend([
        {"role": "user", "text": question},
        {"role": "assistant", **response},
    ])
    st.session_state.conversation_state = next_state
    st.session_state.last_suggestions = response.get("suggestions", [])


def show_answer(message: dict) -> None:
    status = message.get("status")
    if status:
        st.caption(STATUS_LABELS.get(status, "Book-based response"))
    st.write(message.get("text", ""))
    if message.get("details_en"):
        with st.expander("More detail"):
            st.write(message["details_en"])
    cards = message.get("source_cards", [])
    if cards:
        pages = sorted({str(card.get("page", "?")) for card in cards})
        label = f"Read the source · {'page' if len(pages) == 1 else 'pages'} {', '.join(pages)}"
        with st.expander(label):
            st.caption("Wau Tradisional Malaysia: Traditional Kites of Malaysia (2002). Page numbers refer to the printed book.")
            for index, card in enumerate(cards):
                if index:
                    st.divider()
                language = {"en": "English", "ms": "Malay", "malay": "Malay", "english": "English"}.get(card.get("language"), card.get("language", ""))
                st.markdown(f"**Page {escape(str(card.get('page', '?')))} · {escape(str(language))}**")
                st.write(card.get("quote", ""))
                scope = card.get("scope", "")
                # The section title is helpful to a reader; internal source IDs are not.
                if scope:
                    clean_scope = re.sub(r"\bS\d+:\d{4}:\s*", "", str(scope)).strip()
                    st.caption(clean_scope)


def load_study_config() -> dict:
    return json.loads((BASE / "study" / "config.json").read_text(encoding="utf-8"))


def study_is_active(config: dict) -> bool:
    return bool(config.get("collection_enabled") and config.get("approval_status") == "confirmed"
                and str(config.get("approval_reference", "")).strip())


def prepare_response(config: dict, familiarity: str, attempts: list[dict], answers: list[int]) -> dict:
    """Export only deliberate ratings; exclude chat, nickname and device metadata."""
    if len(answers) != 16 or any(type(value) is not int or not 1 <= value <= 5 for value in answers):
        raise ValueError("All 16 questionnaire answers must be integers from 1 to 5.")
    return {"instrument": "WauTrace adapted CUQ", "preview_only": not study_is_active(config),
            "adult_eligibility_confirmed": True, "voluntary_participation_confirmed": True,
            "q0_prior_familiarity": familiarity,
            "task_attempts": [{"task_id": entry["task_id"], "status": entry["status"]} for entry in attempts],
            "responses": [{"item_id": number, "response": value} for number, value in enumerate(answers, 1)]}


def response_csv(payload: dict) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["preview_only", "q0_prior_familiarity", *[f"T{number}_status" for number in range(1, 7)], *[f"CUQ{number:02d}" for number in range(1, 17)]])
    attempts = {item["task_id"]: item["status"] for item in payload["task_attempts"]}
    writer.writerow([payload["preview_only"], payload["q0_prior_familiarity"], *[attempts.get(f"T{number}", "") for number in range(1, 7)], *[item["response"] for item in payload["responses"]]])
    return stream.getvalue()


def clear_study() -> None:
    for key in list(st.session_state):
        if key.startswith("study_") or key.startswith("cuq_"):
            del st.session_state[key]
    st.session_state.study_stage = "closed"
    reset_conversation()


def open_study() -> None:
    st.session_state.study_stage = "intro"


def begin_study() -> None:
    familiarity = st.session_state.get("study_familiarity")
    valid = bool(st.session_state.get("study_adult") and st.session_state.get("study_consent")
                 and familiarity is not None)
    st.session_state.study_entry_error = not valid
    if valid:
        st.session_state.study_q0 = familiarity
        st.session_state.study_stage = "tasks"


def advance_task(status: str) -> None:
    config = load_study_config()
    index = st.session_state.study_task_index
    st.session_state.study_attempts.append({"task_id": config["tasks"][index]["id"], "status": status})
    st.session_state.study_task_index += 1
    if st.session_state.study_task_index >= len(config["tasks"]):
        st.session_state.study_stage = "questionnaire"


def show_study() -> bool:
    """Render an opt-in journey; return whether conversation should be visible."""
    stage = st.session_state.study_stage
    if stage == "closed":
        return True
    config = load_study_config()
    active = study_is_active(config)
    with st.container(border=True):
        st.subheader("Guided visit")
        if not active:
            st.info("Prototype preview · Study approval is pending. These practice responses are not research data.")
        if stage == "intro":
            st.write(f"Allow about {config['estimated_minutes']} minutes. Explore the guide, try six short tasks, then describe your experience. Use your own wording and rate what actually happens.")
            st.write("Participation is voluntary and intended for adults aged 18 or older. You may skip a task, stop, or clear your answers. No name is required. Your chat and nickname are not included in the questionnaire file.")
            if config.get("questionnaire_url"):
                st.caption("After the tasks, open the linked questionnaire. This app does not submit your chat, nickname or answers to that form. The questionnaire explains its own data handling arrangements.")
            else:
                st.caption("Answers remain in this session. Nothing is submitted automatically. At the end you may choose to download a response file. An already downloaded file remains under your control.")
            if config.get("researcher_contact"):
                st.caption(f"Study contact: {config['researcher_contact']}")
            with st.form("study_entry"):
                adult = st.checkbox("I am aged 18 or older.", key="study_adult")
                consent = st.checkbox("I understand the information above and choose to continue voluntarily.", key="study_consent")
                familiarity = st.radio(config["familiarity_question"], config["familiarity_options"], index=None, key="study_familiarity")
                st.form_submit_button("Begin tasks", on_click=begin_study)
            if st.session_state.get("study_entry_error"):
                st.warning("Please confirm both statements and answer the familiarity question to continue, or leave the guided visit.")
        elif stage == "tasks":
            index = st.session_state.study_task_index
            task = config["tasks"][index]
            st.progress(index / len(config["tasks"]), text=f"Task {index + 1} of {len(config['tasks'])}")
            st.markdown(f"**{task['title']}**")
            st.write(task["instruction"])
            st.caption("Use the chat below. Attempted means you tried the task; it does not mean the answer was correct.")
            left, right = st.columns(2)
            left.button("I have attempted this task", key="study_attempt", on_click=advance_task, args=("attempted",), use_container_width=True)
            right.button("Skip this task", key="study_skip", on_click=advance_task, args=("skipped",), use_container_width=True)
        elif stage == "questionnaire":
            st.progress(1.0, text="Tasks finished · Share your experience")
            st.write("Rate your actual experience. There are no right answers. 1 = Strongly disagree; 2 = Disagree; 3 = Neither agree nor disagree; 4 = Agree; 5 = Strongly agree.")
            url = str(config.get("questionnaire_url", "")).strip()
            parsed = urlparse(url)
            if parsed.scheme == "https" and parsed.netloc:
                st.link_button("Open the study questionnaire", url)
                st.caption("Complete the linked questionnaire once. Your answers are entered in that form; this app does not receive or submit them.")
                st.button("I finished the linked questionnaire", key="study_external_done", on_click=lambda: st.session_state.update(study_stage="end"))
            else:
                instrument = json.loads((BASE / "cuq_adapted_instrument.json").read_text(encoding="utf-8"))
                with st.form("study_cuq"):
                    answers = [st.radio(f"{item['item_id']}. {item['english_item']}", [1, 2, 3, 4, 5], index=None, horizontal=True, key=f"cuq_{item['item_id']}") for item in instrument]
                    if st.form_submit_button("Prepare my response"):
                        if any(value is None for value in answers):
                            st.warning("Please answer all 16 items before preparing a response, or choose Withdraw and clear.")
                        else:
                            st.session_state.study_payload = prepare_response(config, st.session_state.study_q0, st.session_state.study_attempts, answers)
                            st.session_state.study_stage = "end"
                            st.rerun()
        elif stage == "end":
            st.success("Thank you. Your guided visit is complete.")
            payload = st.session_state.study_payload
            if payload:
                st.write("Your response has not been submitted. Download it only if you choose, then use the transfer method agreed with the researcher.")
                prefix = "wautrace_preview_response" if payload["preview_only"] else "wautrace_response"
                st.download_button("Download response (JSON)", json.dumps(payload, indent=2), file_name=prefix + ".json", mime="application/json", key="study_download_json")
                st.download_button("Download response (CSV)", response_csv(payload), file_name=prefix + ".csv", mime="text/csv", key="study_download_csv")
            else:
                st.write("Any response submitted through the external questionnaire is handled by that questionnaire. This app has not received it.")
            st.caption("You may now close the page or clear this session. No chatbot conversation is included in a response download.")
        st.button("Withdraw and clear" if stage != "end" else "Clear this session", key="study_clear", on_click=clear_study)
    return stage == "tasks"


def main() -> None:
    st.set_page_config(page_title="WauTrace · A guide to Wau Kikik", page_icon="🪁", layout="centered", initial_sidebar_state="collapsed")
    initialise_session()
    st.markdown("""
<style>
.stApp { background: #faf8f3; }
[data-testid="stSidebar"] { background: #efeee7; }
.block-container { padding-top: 2.1rem; max-width: 880px; }
[data-testid="stChatMessage"] { border: 1px solid #dedfd5; border-radius: 14px; background: #ffffff; }
[data-testid="stChatMessage"] p { line-height: 1.65; }
[data-testid="stChatInput"] { border-color: #697d70; }
h1, h2, h3 { color: #173d31; }
.eyebrow { color: #536653; font-size: .8rem; font-weight: 650; letter-spacing: .12em; text-transform: uppercase; }
.hero-note { color: #44554b; font-size: 1.06rem; line-height: 1.6; max-width: 680px; }
@media (max-width: 640px) { .block-container { padding: 1.25rem 1rem 5rem; } h1 { font-size: 2.1rem; } }
</style>
""", unsafe_allow_html=True)
    with st.sidebar:
        st.markdown("### Your visit")
        st.selectbox("Your timezone", TIMEZONES, key="selected_zone", help="The browser timezone is used automatically. You can override it here. If browser information is unavailable, the greeting uses UTC and says so.")
        with st.form("nickname_form", clear_on_submit=False):
            st.text_input("Nickname (optional)", key="nickname_input", max_chars=40, help="A first name or any nickname is enough. It stays in this session only.")
            st.form_submit_button("Remember nickname", on_click=save_nickname, use_container_width=True)
        if st.session_state.nickname:
            st.caption(f"I'll remember {st.session_state.nickname} during this visit.")
        st.divider()
        st.markdown("#### Start again")
        st.button("Start over", on_click=reset_conversation, use_container_width=True)
        st.caption("Start over clears the conversation, its follow-up context and your nickname. This app does not write your conversation or nickname to a study file.")
        st.divider()
        st.markdown("#### About the source")
        st.write("This guide draws on selected pages of *Wau Tradisional Malaysia: Traditional Kites of Malaysia* (2002).")
        st.caption("Descriptions belong to the book's time and context. The guide cannot confirm today's rules or practices.")
        with st.expander("How to read the answers"):
            st.markdown("- **Documented:** the book supports the answer.\n- **Ruled out:** the book explicitly denies that feature.\n- **Not documented:** the selected pages do not settle it.\n- **Needs context:** wording or source versions differ.")

    current_time, display_zone, clock_source = browser_clock()
    greeting_hour = current_time.hour
    demonstration = os.getenv("WAUTRACE_DEMO_HOUR", "")
    demonstration_active = False
    if demonstration:
        try:
            greeting_hour = int(demonstration)
            if not 0 <= greeting_hour <= 23:
                raise ValueError
            demonstration_active = True
            st.info(f"Demonstration time: {greeting_hour:02d}:00. The greeting below uses a controlled clock for documentation.")
        except ValueError:
            st.warning("The demonstration hour is invalid. The greeting uses the actual local time.")
            greeting_hour = current_time.hour
    st.session_state.greeting_hour = greeting_hour
    st.markdown('<div class="eyebrow">A guide to Malaysian kite heritage</div>', unsafe_allow_html=True)
    st.title("WauTrace")
    st.subheader(time_greeting(greeting_hour, st.session_state.nickname))
    st.caption(f"{display_zone} · {'Demonstration clock' if demonstration_active else current_time.strftime('%H:%M')} · {clock_source}")
    st.markdown('<p class="hero-note">Explore Wau Kikik through the words of a 2002 sourcebook. Ask about its names, forms and features, or the book’s account of Wau Laga.</p>', unsafe_allow_html=True)
    left, right = st.columns(2)
    left.button("Guided visit", key="open_study", on_click=open_study, use_container_width=True, disabled=st.session_state.study_stage != "closed")
    right.button("New chat", key="main_reset", on_click=reset_conversation, use_container_width=True)
    if not show_study():
        return
    if not st.session_state.messages:
        st.info("Welcome. I can show what the book supports, what it rules out, what it does not document, and where its wording differs. Ask a short question or choose a topic below. You can open the source beneath an answer.")
        st.caption('You can say “My name is Sara” if you would like to use a nickname. A name is optional and stays in this session.')
    with st.expander("Explore a topic", expanded=False):
        for row in (TOPICS[:4], TOPICS[4:]):
            columns = st.columns(4)
            for column, (label, question) in zip(columns, row):
                with column:
                    st.button(label, key=f"topic_{label.lower().replace(' ', '_')}", on_click=submit_question, args=(question,), use_container_width=True)
    for message in st.session_state.messages:
        with st.chat_message(message["role"], avatar="🪁" if message["role"] == "assistant" else None):
            if message["role"] == "assistant":
                show_answer(message)
            else:
                st.write(message["text"])
    if st.session_state.last_suggestions:
        last_reply = next((message for message in reversed(st.session_state.messages)
                           if message["role"] == "assistant"), {})
        st.caption("Choose an option:" if last_reply.get("status") == "clarification" else "You could ask:")
        for index, suggestion in enumerate(st.session_state.last_suggestions[:3]):
            st.button(str(suggestion), key=f"suggestion_{index}", on_click=submit_question, args=(str(suggestion),), use_container_width=True)
    question = st.chat_input("Ask about Wau Kikik or the book’s account of Wau Laga…", max_chars=500)
    if question:
        submit_question(question)
        st.rerun()


if __name__ == "__main__":
    main()
