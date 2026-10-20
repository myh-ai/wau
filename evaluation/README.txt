WAUTRACE EVALUATION

Development checks
The 24 cases in ../test_scenarios.json are known development regression examples. They do not estimate independent RQ2 accuracy. Run python run_scenarios.py from the package directory to collect current outputs and bounded machine checks. Human semantic review is separate. The default destination is development_results/ and existing output is not overwritten.

Independent RQ2 evaluation
Read RQ2_PROTOCOL.txt. question_collection_template.json contains 72 empty slots and a collection declaration. Questions and their gold criteria must be independently authored after the build lock. rq2_tool.py registers the completed dataset, verifies the locked artifacts, permits a single execution, exports literal answers and prepares manual scoring fields. test_rq2_tool.py checks collection, hash and scoring safeguards using synthetic fixtures, not cultural evaluation questions.

Current formal results
Question collection and scoring are pending. No independent RQ2 accuracy, participant usability result or learning outcome is asserted.

Conversation development checks
conversation_development.json and .html contain the complete 32-turn development dialogue and its current responses. test_conversation.py checks related paraphrases, topic switches and clarification behaviour. development_questions.json lists literal questions exercised by the development suites and recorded scenarios; the independent evaluation tool rejects exact overlap. These are development materials, not independent RQ2 observations.

fixlist_development.json and .html record the requested question-handling checks and their actual responses. Setup turns, source cards and evidence-state checks are included. These are exposed development cases, also listed in development_questions.json; they are not independent RQ2 evidence.

scope_routing_development.json and .html record class-quantifier, subtype-exception, control-context and material-scope development checks. They include actual answers, setup context and source cards; all questions are exposed development material.
