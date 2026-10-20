# WauTrace

An English, source-bound cultural chatbot about Wau Kikik and the book's distinct Wau Laga naming and playing contexts. The application runs locally in Streamlit without an API key. It uses a semantic network with attached source quotations, scope limits and response compositions. Linguistic routing is application logic; no external language model supplies runtime facts.

## Open the application

Extract the complete ZIP. On Windows, with Python 3.11 or 3.12 installed, double-click `start_windows.bat`. Keep the terminal open. The initial dependency installation needs an internet connection. See `RUN_WAUTRACE.txt` for manual commands. Verification was performed on Linux; the Windows launcher is supplied but was not executed on Windows.

The greeting uses the browser timezone or browser UTC offset, with an explicitly labelled UTC fallback. The sidebar starts collapsed. A manual timezone override is available. A nickname can be supplied in the chat or in the visit settings. Names and conversation context stay in the session; New chat clears them.

The engine normalizes common inflections, contractions and spelling variations, then scores linguistic concepts and graph response facets. Clarification retains the requested property until the missing choice is supplied; a new explicit question selects its own topic. Replies distinguish support, explicit negation, missing evidence and source wording that needs context. Source cards retain exact excerpts. Optional details can be opened separately, and form questions expose three direct choices. Suggestions depend on the conversation topic. Input handling remains bounded; successful development checks do not establish unrestricted language understanding.

## Guided visit and usability study

Choose **Guided visit** for adult eligibility and voluntary participation, one prior-familiarity question, six tasks using participants' own wording, the configured Google questionnaire and an end screen. The app does not submit questionnaire responses or conversation data automatically. The Google Form is the study instrument; its own response handling applies.

`study/config.json` contains the supplied questionnaire URL, https://forms.gle/vHHtfYTKqShZF1zc8, and keeps application collection disabled (`collection_enabled: false`). `study/README.txt` describes the external questionnaire route. Lecturer and institutional study arrangements remain pending; the application does not certify approval or completion of the external form.

CUQ measures perceived usability. Q0 describes prior familiarity; it is not a learning outcome measure. The complete instrument stays in the separate study materials, not in the paper or its appendix. Odd items are positive and even items negative. The adapted wording has not undergone a separate psychometric validation.

## Knowledge and author review

The package contains 36 source records, 74 assertion edges, 83 nodes and 73 semantic fact groups. Counts describe the representation, not its accuracy or cultural completeness.

`knowledge.json` holds the source records. `WauTrace_Network_Template.json` holds the operational semantic network, evidence and response compositions. Every relation retains its subject, predicate, object, polarity, source scope and evidence. The 2002 book is not evidence of current practice or legal permission. Kemetek is an unverified candidate, not a traversable alias. Majority statements do not become universal inherited facts.

`author_review.json` documents the source-claim review. `reviews/author_review_translation_en.json` is explicitly an English translation of the submitted review. `reviews/operational_claim_review.json` contains the author’s 74 approved decisions and is preserved byte-for-byte; its HTML companion displays the same decisions and reasons. The external review binds each assertion to its exact content while the network and knowledge facts remain unchanged. `reviews/response_composition_review.html` presents the current response wording and its evidence; all response-profile decisions remain pending. Approval of the assertions does not imply approval of the response compositions or independent RQ2 results.

The genuine extraction materials in `extraction_runs/full_p73/` contain the supplied passage, exact prompt, literal output, screenshots and source correction table. They support the required passage–extraction–correction method demonstration. They are not a chatbot performance benchmark. Full book scans are not redistributed.

## Development checks and independent RQ2

`test_scenarios.json` and `.html` contain 24 **development regression** cases. Their execution, together with unit tests and additional development checks, is implementation evidence only. None is an unseen or independent estimate of RQ2 accuracy. See `evaluation/development_results/` for the current recorded responses and machine checks. `evaluation/additional_development.html` provides 69 single-question development sessions and 11 conversations, with 96 total turns, for review. These examples are also development material. `evaluation/conversation_development.html` contains the complete 32-turn development conversation; `test_conversation.py` checks related paraphrases and context changes. `test_fixlist.py` checks the requested routing, clarification and wording requirements; `evaluation/fixlist_development.html` presents the corresponding development responses. These are exposed development examples. `evaluation/development_questions.json` records literal questions exposed during development. `evaluation/scope_routing_development.html` and `test_scope_routing.py` cover class quantifiers, explicit subtype exceptions, control context and glass-string description/preparation boundaries.

`evaluation/RQ2_PROTOCOL.txt` defines a separate, pending evaluation: 72 independently authored turns in 66 sessions, including six two-turn dialogues and 12 out-of-scope controls. Questions and gold criteria are supplied by evaluators after the complete runtime and knowledge are frozen. No independent question set, participant results or RQ2 accuracy is supplied in this package.

`evaluation/rq2_tool.py` checks the build lock, registers the question/rubric file, records a single execution without overwriting it, and calculates results only after completed manual scoring. The scoring distinguishes complete, partial, wrong and abstained answers; coverage and correctness have separate denominators. Post-execution changes require a new independent evaluation and cannot validate the same exposed questions. Read the protocol before freezing or collecting questions.

## Documents and figure

- `documents/WauTrace_Assignment_Plan_EN.docx`: questions, method, Algorithms 1–3, participant procedure and writing plan.
- `documents/WauTrace_Step1_Research_Package_EN.docx`: source findings, representation, system materials and evaluation design.
- `graphs/publication_semantic_network.png`, `.svg`, `.pdf`: the selected black-and-white paper figure.
- `graphs/publication_edge_sources.json` and `.csv`: evidence mapping for the selected figure.
- `screenshots/greeting_morning_evening.png`: actual interface captures under visibly labelled controlled clocks, combined for the paper.

These are working research materials, not a completed results paper. The chatbot system section is planned as the main contribution. All claims about results must use actual recorded and reviewed observations.

## Verify and export

```text
python validate_knowledge.py
python knowledge_regression_checks.py
python test_export_graph.py --report graph_export_report.json
python -m unittest test_engine test_app test_conversation test_fixlist test_scope_routing
python run_scenarios.py --output-dir ../WauTrace_development_check
```

The scenario output directory must not already exist; select an empty destination for your check. Read each tool's help before choosing an output destination. Original-page integrity checks can use the five source images separately. The complete graph exports preserve operational IDs and metadata. `GRAPH_README.txt` explains the exports and figure. Structural validation is not a semantic accuracy test. `SHA256SUMS.json` inventories the delivered files.

## Submission status

The author-transcribed Moodle deadline is **Friday, 23 October 2026, 11:45 PM as displayed**, with PDF required. The display timezone is unconfirmed. See `submission_requirements.json`. CJLT is a provisional format candidate; lecturer confirmation, page-count interpretation, study arrangements and publication conditions remain pending. No public deployment or assignment submission has been performed.
