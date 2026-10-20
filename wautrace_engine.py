"""Deterministic linguistic routing over a source-bound semantic network.

Cultural answers, scopes and evidence boundaries are network data. This module
normalizes language, ranks facets and manages conversation state. It does not
make external requests, generate new facts or use a question/answer lookup.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from graph_inference import deduplicate_answers, resolve_feature

ROOT = Path(__file__).resolve().parent


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _surface(text, settings):
    text = unicodedata.normalize("NFKC", str(text)).casefold().replace("’", "'")
    for contraction, expanded in settings.get("contractions", {}).items():
        text = re.sub(r"(?<!\w)" + re.escape(contraction) + r"(?!\w)", expanded, text)
    for phrase in settings.get("discourse_phrases", []):
        text = re.sub(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", " ", text)
    text = re.sub(r"\b(\w+)'s\b", r"\1", text)
    text = re.sub(r"\b([1-9])(?:st|nd|rd|th)\b", r"\1", text)
    text = re.sub(r"[^\w\s'-]", " ", text, flags=re.UNICODE)
    return " ".join(text.replace("-", " ").split())


def _distance_one(a, b):
    """Whether two different words are one insertion, deletion or replacement apart."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1 or any(
            a[:i] + a[i + 1] + a[i] + a[i + 2:] == b for i in range(len(a) - 1))
    shorter, longer = sorted((a, b), key=len)
    return any(longer[:i] + longer[i + 1:] == shorter for i in range(len(longer)))


class LinguisticRouter:
    """Inspectible token normalization and weighted facet selection."""

    def __init__(self, rules):
        self.rules = rules
        self.settings = rules["normalization"]
        raw_terms = [term for terms in rules["concepts"].values() for term in terms]
        raw_terms += [term for terms in rules["entities"].values() for term in terms]
        self.vocabulary = set(" ".join(_surface(x, self.settings) for x in raw_terms).split())
        self.vocabulary |= set(self.settings["irregular"].values())
        self.vocabulary |= set(rules["domain_tokens"]) | set(rules["generic_stop_tokens"])
        self.concepts = {key: [self.tokens(term, correct_typos=False)[0] for term in terms]
                         for key, terms in rules["concepts"].items()}
        self.entities = {key: [self.tokens(term, correct_typos=False)[0] for term in terms]
                         for key, terms in rules["entities"].items()}

    def lemma(self, word):
        if word in self.settings["irregular"]:
            return self.settings["irregular"][word]
        if word in self.settings["orthography"]:
            return self.settings["orthography"][word]
        candidates = []
        if word.endswith("ies") and len(word) > 4:
            candidates.append(word[:-3] + "y")
        for suffix in ("ing", "ied", "ed", "es", "s"):
            if word.endswith(suffix) and len(word) > len(suffix) + 2:
                stem = word[:-len(suffix)]
                candidates += [stem, stem + "e"]
                if len(stem) > 2 and stem[-1] == stem[-2]:
                    candidates.append(stem[:-1])
        # Suffix removal is allowed only if it reaches a known lexical item.
        return next((item for item in candidates if item in self.vocabulary), word)

    def tokens(self, text, correct_typos=True):
        surface = _surface(text, self.settings)
        result, corrections = [], []
        words = surface.split()
        for index, word in enumerate(words):
            lemma = self.lemma(word)
            # A short domain prefix is corrected only beside a recognized
            # subtype. Ordinary short words are never globally fuzzy-matched.
            if correct_typos and index + 1 < len(words):
                for prefix, following in self.settings.get("contextual_typo_prefixes", {}).items():
                    if (word not in self.vocabulary and word[0:1] == prefix[0:1]
                            and self.lemma(words[index + 1]) in following and _distance_one(word, prefix)):
                        corrections.append({"input": word, "normalized": prefix})
                        lemma = prefix
            if correct_typos and lemma not in self.vocabulary and len(lemma) >= 4:
                candidates = [term for term in self.settings["domain_typo_vocabulary"]
                              if lemma[0] == term[0] and _distance_one(lemma, term)]
                # Ambiguous corrections are never silently selected. Protected
                # documented/candidate names are not corrected into other names.
                if len(candidates) == 1 and lemma not in self.settings["protected_names"]:
                    corrections.append({"input": word, "normalized": candidates[0]})
                    lemma = candidates[0]
            result.append(lemma)
        return result, corrections

    @staticmethod
    def contains(tokens, phrase):
        return bool(phrase) and any(tokens[i:i + len(phrase)] == phrase
                                   for i in range(len(tokens) - len(phrase) + 1))

    def analyze(self, message):
        tokens, corrections = self.tokens(message)
        concepts = {key for key, phrases in self.concepts.items()
                    if any(self.contains(tokens, phrase) for phrase in phrases)}
        surface = _surface(message, self.settings)
        for key, patterns in self.rules.get("structural_concepts", {}).items():
            if any(re.search(pattern, surface) for pattern in patterns):
                concepts.add(key)
        # The head noun determines what a kind/type denotes. A kind of string
        # is a material question, not one of the source's numbered kite forms.
        if "material_kind" in concepts and not set(tokens) & {"form", "shape", "design", "variant"}:
            concepts.discard("forms")
            concepts.discard("form_collection")
        # A feature's adjective (leaf-shaped wings) is not a numbered kite
        # form. Only an independent form/type/shape noun can request ranking.
        form_tokens = list(tokens)
        for phrase in self.settings.get("feature_shape_phrases", []):
            phrase_tokens = self.tokens(phrase, correct_typos=False)[0]
            while self.contains(form_tokens, phrase_tokens):
                index = next(i for i in range(len(form_tokens))
                             if form_tokens[i:i + len(phrase_tokens)] == phrase_tokens)
                del form_tokens[index:index + len(phrase_tokens)]
        explicit_form_reference = bool(set(form_tokens) & set(self.settings.get("form_reference_words", [])))
        if not explicit_form_reference:
            concepts.discard("forms")
            concepts.discard("form_collection")
        entities = {key for key, phrases in self.entities.items()
                    if any(self.contains(tokens, phrase) for phrase in phrases)}
        # A named subtype takes precedence over the incidental class phrase.
        if entities & {"wau_kikik", "kaca", "wau_laga"}:
            entities.discard("traditional_malay_wau")
        ordinal = next((self.settings["ordinals"][word] for word in tokens
                        if word in self.settings["ordinals"]), None)
        if ordinal is None:
            number_tokens = [str(self.settings.get("spelled_numbers", {}).get(token, token)) for token in tokens]
            ordinal = next((int(token) for i, token in enumerate(number_tokens)
                            if token in {"1", "2", "3"} and (
                                re.search(r"\b" + token + r"(?:st|nd|rd|th)\b", str(message).lower())
                                or (i > 0 and tokens[i - 1] in {"form", "type", "number"}))), None)
        return {"surface": surface, "original": str(message), "tokens": tokens, "concepts": concepts,
                "entities": entities, "ordinal": ordinal, "corrections": corrections,
                "explicit_form_reference": explicit_form_reference}

    def rank(self, analysis, state):
        concepts, entities = analysis["concepts"], set(analysis["entities"])
        context_entity = state.get("entity")
        if not entities and context_entity:
            entities.add(context_entity)
        if "kaca" in entities:
            entities.add("wau_kikik")
        if {"wau_kikik", "wau_laga"} <= entities:
            entities.add("laga_pair")
        # Facets provide a default source context when a fresh question names a
        # distinctive feature or procedure, without requiring a literal 'wau'.
        if not entities:
            entities.add("wau_kikik")
        scored = {}
        for route in self.rules["routes"]:
            required = set(route["all"])
            if route["profile"] == "overview":
                generic_tokens = set(self.rules["generic_stop_tokens"]) | set(self.rules["domain_tokens"]) | {"describe", "explain"}
                if set(analysis["tokens"]) - generic_tokens:
                    continue
            any_required = set(route["any"])
            if not required <= concepts or (any_required and not any_required & concepts):
                continue
            if set(route["forbid"]) & concepts:
                continue
            if route.get("entity") and route["entity"] not in entities:
                continue
            if route.get("bare_only"):
                allowed = set(self.rules["generic_stop_tokens"]) | set(self.rules["domain_tokens"])
                if not analysis["entities"] or concepts - {"overview", "followup"} or set(analysis["tokens"]) - allowed:
                    continue
            context = route.get("context")
            if context and context not in {state.get("referent"), state.get("last_intent"), state.get("last_facet")}:
                continue
            score = route["bias"] + 2 * len(required) + 2 * len(any_required & concepts)
            score += sum(weight for key, weight in route["weights"].items() if key in concepts)
            if route.get("entity") and route["entity"] in analysis["entities"]:
                score += 1
            item = {"profile": route["profile"], "score": score,
                    "matched_concepts": sorted((required | any_required | set(route["weights"])) & concepts)}
            if item["profile"] not in scored or score > scored[item["profile"]]["score"]:
                scored[item["profile"]] = item
        return sorted(scored.values(), key=lambda item: (-item["score"], item["profile"]))


def normalize(text):
    """Public normalized-token helper; uses the same configuration as routing."""
    router = LinguisticRouter(_read(ROOT / "language_rules.json"))
    return " ".join(router.tokens(text)[0])


class WauTraceEngine:
    """Pure request/response interface; callers retain session state in memory."""

    def __init__(self, network_path=None, language_path=None, review_path=None):
        network_path = Path(network_path or ROOT / "WauTrace_Network_Template.json")
        self.network = _read(network_path)
        self.rules = _read(language_path or ROOT / "language_rules.json")
        self.router = LinguisticRouter(self.rules)
        self.catalog = self.network["response_catalog"]
        self.profiles = self.catalog["profiles"]
        self.edges = {edge["edge_id"]: edge for edge in self.network["edges"]
                      if edge.get("source_review_status") == "source_checked"
                      and edge.get("prototype_eligible") is True and edge.get("evidence")
                      and edge.get("author_decision") not in {"rejected", "reject", "deferred"}}
        self.approved_edge_ids = self._reviewed_edges(Path(review_path) if review_path else network_path.parent / "reviews" / "operational_claim_review.json")
        self._validate_catalog()

    def _reviewed_edges(self, path):
        """Bind external author decisions to exact immutable assertion content."""
        if not path.is_file():
            return set()
        review = _read(path)
        rows = review.get("claims", [])
        claims = {row.get("edge_id"): row for row in rows}
        edges = {edge["edge_id"]: edge for edge in self.network["edges"]}
        if len(claims) != len(rows) or set(claims) != set(edges):
            return set()
        records = {record["record_id"]: record for record in self.network["record_catalog"]}
        approved = set()
        for edge_id, edge in edges.items():
            row = claims[edge_id]
            evidence = [{key: value for key, value in item.items() if key in {"page", "language", "quote"}} for item in edge["evidence"]]
            if any(row.get(key) != edge.get(key) for key in ("record_id", "subject", "relation", "polarity", "status", "scope", "answer_en")):
                return set()
            if row.get("object") != edge["kb_triple"]["object"] or row.get("limits_en") != records[edge["record_id"]]["limits_en"] or row.get("evidence") != evidence:
                return set()
            if row.get("author_decision") == "approved" and all(str(row.get(key) or "").strip() for key in ("decision_reason", "author_reviewer", "author_review_date")):
                approved.add(edge_id)
        return approved

    def _select(self, selectors):
        selected = {}
        for selector in selectors:
            for edge in self.edges.values():
                if all(edge.get(key) == value for key, value in selector.items()):
                    selected[edge["edge_id"]] = edge
        return list(selected.values())

    def _validate_catalog(self):
        for profile_id, profile in self.profiles.items():
            for selector in profile.get("selectors", []):
                if not self._select([selector]):
                    raise ValueError(f"Response profile {profile_id} has an unresolved source selector: {selector}")
        for route in self.rules["routes"]:
            if route["profile"] not in self.profiles:
                raise ValueError(f"Missing response profile: {route['profile']}")

    def _expand(self, edges):
        todo, expanded = list(edges), {}
        while todo:
            edge = todo.pop(0)
            if edge["edge_id"] in expanded:
                continue
            expanded[edge["edge_id"]] = edge
            todo += [self.edges[eid] for eid in edge.get("required_context_edge_ids", [])
                     if eid in self.edges and eid not in expanded]
        return list(expanded.values())

    def _cards(self, edges):
        cards = {}
        for edge in edges:
            scope = re.sub(r"^[A-Za-z]+[0-9]+:(?:\d{4}:)?", "", edge.get("scope", "")).strip()
            for quote in edge.get("evidence", []):
                key = tuple(quote.get(k) for k in ("source_id", "page", "language", "quote"))
                card = cards.setdefault(key, {**{k: quote[k] for k in ("source_id", "page", "language", "quote")},
                                             "scope": scope, "scopes": [], "edge_ids": []})
                if scope not in card["scopes"]:
                    card["scopes"].append(scope)
                card["edge_ids"].append(edge["edge_id"])
        for card in cards.values():
            card["edge_ids"] = sorted(set(card["edge_ids"]))
            card["scope"] = " | ".join(card["scopes"])
        return list(cards.values())

    def _suggest(self, state, intent, text):
        seen = set(state.get("visited_intents", []))
        pool = [item for item in self.catalog["suggestions"] if item["topic"] != intent
                and self.router.tokens(item["text"])[0] != self.router.tokens(text)[0]]
        pool.sort(key=lambda item: item["topic"] in seen)
        return [item["text"] for item in pool[:self.rules["routing"]["maximum_suggestions"]]]

    def _reply(self, state, text, status, intent=None, edges=(), suggestions=None, trace=None):
        state = dict(state)
        edges = self._expand(list(edges))
        cards = self._cards(edges)
        if status not in {"clarification", "system"}:
            state["last_status"] = status
            state["last_intent"] = intent
            state["last_edge_ids"] = [edge["edge_id"] for edge in edges]
            state["last_source_cards"] = cards
            state["last_answer"] = text
            state["visited_intents"] = list(dict.fromkeys(state.get("visited_intents", []) + [intent]))[-12:]
        response = {"text": text, "status": status, "intent": intent,
                    "source_cards": cards, "edge_ids": [edge["edge_id"] for edge in edges],
                    "record_ids": sorted({edge["record_id"] for edge in edges}), "state": state,
                    "suggestions": suggestions if suggestions is not None else self._suggest(state, intent, text),
                    "review_status": ("source_checked_author_approved" if edges and all(e["edge_id"] in self.approved_edge_ids for e in edges) and self.catalog.get("review_status") == "approved" else "source_checked_representation_pending" if edges else "not_applicable"),
                    "author_review_status": ("approved" if edges and all(e["edge_id"] in self.approved_edge_ids for e in edges) else "pending" if edges else "not_applicable"),
                    "routing": trace or {}}
        return response

    def _profile(self, profile_id, state, trace=None, extra_profiles=()):
        profile = self.profiles[profile_id]
        trace = dict(trace or {}, selected_profile=profile_id)
        selected = self._select(profile.get("selectors", []))
        resolution = None
        query = profile.get("graph_query")
        if query:
            if query["operation"] != "resolve_feature":
                raise ValueError("Unsupported graph query operation")
            eligible_network = {"edges": list(self.edges.values())}
            resolution = resolve_feature(eligible_network, query["subject"], query["feature"], query.get("source_id", "S01"))
            selected_ids = list(resolution["source_edge_ids"])
            if query.get("include_class_context"):
                selected_ids += resolution["class_context_edge_ids"] + resolution["membership_edge_ids"]
            selected = [self.edges[eid] for eid in dict.fromkeys(selected_ids)]
            trace["graph_inference"] = {key: resolution[key] for key in (
                "status", "value", "quantifier", "source_edge_ids", "class_context_edge_ids",
                "membership_edge_ids", "inherited_as_subtype_fact", "class_candidate_action")}
        if profile.get("reuse_previous_evidence"):
            selected += [self.edges[eid] for eid in state.get("last_edge_ids", []) if eid in self.edges]
        texts = []
        for key in [*extra_profiles, profile_id]:
            item = self.profiles[key]
            item_edges = self._select(item.get("selectors", []))
            selected += item_edges
            text = item.get("text")
            form_label = self.rules["normalization"].get("form_labels", {}).get(str(state.get("form_number")))
            component = state.get("requested_component")
            if item.get("text_template") and form_label and component in {"head", "tail"}:
                text = item["text_template"].format(form_label=form_label, component=component)
            if text is None:
                text = " ".join(dict.fromkeys(answer["answer_en"] for answer in deduplicate_answers(item_edges)))
            texts.append(text)
        text = " ".join(dict.fromkeys(texts))
        statuses = {edge["status"] for edge in selected}
        status = (resolution["status"] if resolution else profile.get("status")) or (
            "source_variance" if "source_variance" in statuses else
            "explicit_negative" if "explicit_negative" in statuses else "supported")
        state = dict(state, last_facet=profile_id)
        for key in ("entity", "referent", "form_number"):
            if key in profile:
                state[key] = profile[key]
        if "form_number" not in profile and not profile.get("preserve_form_context"):
            state.pop("form_number", None)
        state.pop("requested_component", None)
        state.pop("pending_clarification", None)
        state.pop("pending_question", None)
        # A name is used gently, on the first substantive answer after it is set.
        if state.get("nickname") and not state.get("name_used_in_answer"):
            text = state["nickname"] + ", " + text[0].lower() + text[1:]
            state["name_used_in_answer"] = True
        response = self._reply(state, text, status, profile["intent"],
                               list({e["edge_id"]: e for e in selected}.values()),
                               suggestions=profile.get("suggestions"), trace=trace)
        if profile.get("details_en"):
            response["details_en"] = profile["details_en"]
        return response

    def _clarify(self, state, clarification, trace=None, candidates=None, question=None):
        entry = self.catalog["clarifications"][clarification]
        state = dict(state, pending_clarification=clarification)
        if question:
            state["pending_question"] = question
        else:
            state.pop("pending_question", None)
        reply = self._reply(state, entry["text"], "clarification", suggestions=[item["label"] for item in entry["choices"]] or None, trace=trace)
        if candidates:
            reply["intent_candidates"] = candidates
        return reply

    def _system(self, state, key):
        hour = state.get("local_hour")
        greeting = ("Good morning" if isinstance(hour, int) and 5 <= hour < 12 else
                    "Good afternoon" if isinstance(hour, int) and 12 <= hour < 18 else
                    "Good evening" if isinstance(hour, int) else "Hello")
        nickname = state.get("nickname", "")
        text = self.catalog["messages"][key].format(nickname=nickname, name=(", " + nickname if nickname else ""), greeting=greeting)
        return self._reply(state, text, "system")

    def _social(self, message, state, analysis):
        surface = analysis["surface"]
        if surface in self.rules["social"]["reset"]:
            response = self._system({}, "reset")
            response["reset"] = True
            return response
        if not surface:
            return self._reply(state, self.catalog["messages"]["empty"], "clarification")
        if surface in self.rules["social"].get("help", []) or any(
                re.fullmatch(pattern, surface) for pattern in self.rules.get("social_patterns", {}).get("help", [])):
            return self._system(state, "help")
        if re.search(r"\b(?:what|remember|know|recall)\b.*\bmy name\b|\bmy name\b.*\b(?:what|remember|know)\b", surface):
            return self._system(state, "name_recalled" if state.get("nickname") else "name_missing")
        name_match = re.match(r"\s*(?:my name is|call me|please call me|i am|i'm)\s+([^.!?,;\n]+)[.!?]*\s*$", message, re.I)
        if name_match:
            name = name_match.group(1).strip()
            blocked = set(self.rules.get("non_name_words", [])) | set(self.rules["domain_tokens"])
            if (1 <= len(name) <= 40 and len(name.split()) <= 3 and
                    all(part.replace("'", "").replace("’", "").replace("-", "").isalpha() for part in name.split())
                    and not (set(name.casefold().split()) & blocked)):
                state = dict(state, nickname=name, name_used_in_answer=False)
                state.pop("pending_name", None)
                return self._system(state, "name_saved")
        for key in ("greeting", "thanks", "bye"):
            if surface in self.rules["social"][key] or any(re.match(pattern, surface) for pattern in self.rules.get("social_patterns", {}).get(key, [])):
                return self._system(state, {"greeting": "hello", "thanks": "thanks", "bye": "bye"}[key])
        return None

    def _location_request(self, analysis):
        """Recognize geographic questions without turning every 'in' into a place.

        Source-backed locations live on response profiles. This parser only
        distinguishes an expressed location argument from procedural, temporal
        and source-language phrases; it never supplies geographic facts.
        """
        settings = self.rules["location_query"]
        surface, concepts = analysis["surface"], analysis["concepts"]
        geography = any(re.search(pattern, surface) for pattern in settings["patterns"])
        prepositions = list(settings["prepositions"])
        if concepts & {"official_status", "popularity"}:
            prepositions += settings["relation_prepositions"]
        prep = "|".join(re.escape(word) for word in prepositions)
        candidates = []
        for match in re.finditer(settings["possessive_place_pattern"], analysis["original"].casefold()):
            phrase_tokens, _ = self.router.tokens(match.group(1))
            phrase = " ".join(token for token in phrase_tokens if token not in self.rules["generic_stop_tokens"]
                              and token not in self.rules["domain_tokens"])
            if phrase:
                candidates.append(phrase)
        for match in re.finditer(r"\b(?:" + prep + r")\s+(.+?)(?=\s+(?:and|or)\b|$)", surface):
            if match.group(0).strip() in settings["non_spatial_phrases"]:
                continue
            phrase = match.group(1).strip()
            for modifier in settings["trailing_modifiers"]:
                phrase = re.sub(r"\s+" + re.escape(modifier) + r"$", "", phrase).strip()
            if not phrase or any(phrase == item or phrase.startswith(item + " ")
                                 for item in settings["excluded_phrases"]):
                continue
            # Numeric measurements and ordinary procedure arguments (e.g.
            # 'from spinning' or 'in the desired direction') are not toponyms.
            phrase_analysis = self.router.analyze(phrase)
            if any(word.isdigit() for word in phrase_analysis["tokens"]):
                continue
            meaningful = set(phrase_analysis["tokens"]) - set(self.rules["generic_stop_tokens"])
            known_procedure = phrase_analysis["concepts"] & {
                "prepare", "direction", "control", "height", "distance", "wind",
                "stability", "dive", "defence", "attack", "forms", "people", "launch",
                "string", "glass", "hummer", "sobek", "wings", "covering", "book"}
            if known_procedure and not geography:
                continue
            if meaningful and not phrase_analysis["entities"]:
                candidates.append(phrase)
        explicit_geography = any(word in analysis["tokens"] for word in settings["geography_words"])
        where_geography = geography and not (concepts & set(settings["non_geographic_where_concepts"]))
        return {"requested": bool(candidates or explicit_geography or where_geography),
                "places": candidates, "geography": bool(explicit_geography or where_geography)}

    def _location_profile(self, analysis, state, location):
        """Return a profile only for the source's documented relation and scope."""
        concepts = analysis["concepts"]
        entity = state.get("entity")
        # Legal/current queries retain their explicit evidence limits.
        if "legal" in concepts:
            return None
        places = location["places"]
        for profile_id, profile in self.profiles.items():
            scope = profile.get("location_scope")
            if not scope or scope["entity"] != entity:
                continue
            aliases = {" ".join(self.router.tokens(alias)[0]) for alias in scope["aliases"]}
            named_match = bool(places) and all(" ".join(self.router.tokens(place.removeprefix("the "))[0]) in aliases for place in places)
            if profile_id == "official":
                # General 'where' may ask for the documented association. A
                # question about origins or playing there is a different claim.
                official_relation = ("official_status" in concepts or (not places and "official" in concepts)) and not concepts & {"practice", "fly", "origin", "popularity", "exclusive"}
                if official_relation and (named_match or not places):
                    return "official_current" if "current" in concepts else profile_id
            elif profile_id == "popularity":
                geographic_practice = not places and location["geography"] and bool(concepts & {"practice", "fly"})
                if ("popularity" in concepts or geographic_practice) and (named_match or not places) and not concepts & {"current", "universal", "exclusive", "origin"}:
                    return profile_id
        return "place_unknown"

    def respond(self, message, state=None):
        state = dict(state or {})
        message = str(message).strip()[:2000]
        analysis = self.router.analyze(message)
        social = self._social(message, state, analysis)
        if social:
            return social
        # Independent interrogative clauses are handled sequentially. A simple
        # conjunction inside one relation is not split into an invented query.
        clauses = [part.strip() for part in re.split(r"\?\s+|\s+and\s+(?=(?:what|how|who|when|where|why|does|do|is|are)\b)", message, flags=re.I) if part.strip()]
        if 1 < len(clauses) <= self.rules["routing"]["maximum_clauses"]:
            results = []
            for clause in clauses:
                result = self._answer(clause, state)
                state = result["state"]
                results.append(result)
            edges = [self.edges[eid] for result in results for eid in result["edge_ids"] if eid in self.edges]
            precedence = ["clarification", "not_documented", "source_variance", "explicit_negative", "supported", "system"]
            status = next(value for value in precedence if any(r["status"] == value for r in results))
            return self._reply(state, "\n\n".join(dict.fromkeys(r["text"] for r in results)), status, results[-1]["intent"], edges,
                               trace={"clauses": [r["routing"] for r in results]})
        return self._answer(message, state, analysis)

    def _answer(self, message, state, analysis=None):
        a = analysis or self.router.analyze(message)
        c, entities = a["concepts"], a["entities"]
        trace = {"normalized": " ".join(a["tokens"]), "concepts": sorted(c), "entities": sorted(entities),
                 "normalizations": a["corrections"], "method": "weighted_facet_routing"}
        if "outside" in c:
            return self._reply(state, self.catalog["messages"]["out_of_scope"], "not_documented", "not_documented", trace=trace)
        # A clarification fills one missing part of the pending request.
        # It does not erase that request or hijack a different full question.
        pending = state.get("pending_clarification")
        if pending in self.catalog["clarifications"]:
            choices = self.catalog["clarifications"][pending]["choices"]
            compatible = {"overview", "followup", "comparison_followup"}
            compatible.update(concept for choice in choices for concept in choice.get("concepts", []))
            if pending == "importance_scope":
                compatible.add("importance")
            if pending == "form_number":
                compatible |= {"forms", "tail", "head", "geometry"}
            matched = [choice for choice in choices if set(choice.get("concepts", [])) & c
                       or set(choice.get("entities", [])) & entities
                       or (choice.get("ordinal") and choice["ordinal"] == a["ordinal"])]
            choice_entities = set().union(*(set(choice.get("entities", [])) for choice in choices))
            if len(matched) == 1 and not c - compatible and (not entities or entities <= choice_entities):
                choice = matched[0]
                saved = state.pop("pending_question", None)
                state.pop("pending_clarification", None)
                trace["selection"] = "clarification_choice"
                if "clarification" in choice:
                    return self._clarify(state, choice["clarification"], trace)
                if saved:
                    continued = self.router.analyze(saved["message"])
                    chosen_profile = self.profiles[choice["profile"]]
                    if pending == "form_number":
                        continued["ordinal"] = choice["ordinal"]
                        continued["concepts"].add("forms")
                    elif pending == "wau_scope":
                        continued["entities"] = {chosen_profile["entity"]}
                    trace["selection"] = "clarification_completed_request"
                    reply = self._answer(saved["message"], state, continued)
                    reply["routing"]["selection"] = trace["selection"]
                    return reply
                return self._profile(choice["profile"], state, trace)
            if entities or c - compatible or re.match(r"^(?:what|when|why|where|who|how|does|do|is|are|can)\b", a["surface"]):
                state.pop("pending_clarification", None)
                state.pop("pending_question", None)
        if "kemetek" in entities:
            return self._profile("kemetek", state, trace)
        # An unfamiliar named wau cannot inherit the default Kikik subject.
        # Known words after 'wau' (paper, string, question verbs) are ordinary
        # arguments, not new subtype names. This guard adds no domain facts.
        unknown_name = next((word for prior, word in zip(a["tokens"], a["tokens"][1:])
                             if prior == "wau" and word.isalpha()
                             and word not in self.router.vocabulary
                             and word not in self.rules["normalization"].get("non_name_followers", [])), None)
        if unknown_name:
            state["unknown_named_wau"] = unknown_name
            for key in ("entity", "referent", "form_number"):
                state.pop(key, None)
            return self._profile("source_unknown", state, trace)
        if entities:
            state.pop("unknown_named_wau", None)
        elif state.get("unknown_named_wau") and c & {
                "wings", "hummer", "sobek", "forms", "head", "tail", "covering",
                "geometry", "classify", "origin", "distinctive"}:
            return self._profile("source_unknown", state, trace)
        # Provenance follows the actual prior answer, including evidence gaps.
        substantive = c - {"page", "followup", "overview", "official"}
        if "page" in c and not entities and not substantive and state.get("last_answer"):
            selected = [self.edges[eid] for eid in state.get("last_edge_ids", []) if eid in self.edges]
            if state.get("last_status") == "not_documented":
                return self._reply(state, self.catalog["messages"]["no_source"] + " " + state["last_answer"], "not_documented", state.get("last_intent"), trace=trace)
            return self._reply(state, state["last_answer"], state["last_status"], state.get("last_intent"), selected, trace=trace)
        if entities:
            if "kaca" in entities or "wau_kikik" in entities:
                state["entity"] = "wau_kikik"
            elif "wau_laga" in entities:
                state["entity"] = "wau_laga"
            elif "traditional_malay_wau" in entities:
                state["entity"] = "traditional_malay_wau"
        # An explicit subtype follow-up may retain the just-discussed feature,
        # while the graph resolves that feature for the newly named subject.
        if (state.get("referent") == "leaf_shaped_wings" and entities
                and c & {"feature_pronoun", "comparison_followup"}
                and not c & {"forms", "head", "tail", "hummer", "sobek", "covering", "geometry"}):
            c.add("wings")
            trace["concepts"] = sorted(c)
        if "wau_definition" in c:
            return self._profile("wau_definition", state, trace)
        if "age_suitability" in c:
            return self._profile("age_suitability", state, trace)
        if "negative_reason" in c and not entities and state.get("last_status") == "explicit_negative":
            return self._profile("exclusion_reason", state, trace)
        if "sequence_followup" in c and not entities and state.get("last_intent") == "launch" and not c - {"sequence_followup", "overview", "followup", "comparison_followup"}:
            return self._profile("launch_process", state, trace)
        height_context = state.get("last_facet") in {"height", "height_separation", "legal_height"}
        if ("height" in c or height_context) and c & {"legal", "normative", "permission_request"}:
            return self._profile("legal_height", state, trace)
        if "origin" in c and (entities or state.get("entity") or set(a["tokens"]) & set(self.rules["domain_tokens"])):
            profile = "origin_place" if "origin_place" in c and state.get("entity") == "wau_kikik" else "origin"
            return self._profile(profile, state, trace)
        if "event_use" in c and (entities or state.get("entity")):
            return self._profile("source_unknown", state, trace)
        if "current" in c and (entities or state.get("entity") or set(a["tokens"]) & set(self.rules["domain_tokens"])):
            if not c & {"glass", "string", "official_status", "legal"} and not (state.get("referent") == "glass_string" and "universal" in c):
                return self._profile("practice_current", state, trace)
        if "eddy_comparison" in c and "classify" not in c:
            return self._profile("eddy", state, trace)
        # Class-level wording cannot silently inherit facts about one subtype.
        if state.get("entity") == "traditional_malay_wau" and not entities & {"wau_kikik", "kaca", "wau_laga"}:
            if "wings" in c and not c & {"wingless", "silence"}:
                return self._profile("class_wings", state, trace)
            if c & {"hummer", "sobek", "head", "tail", "forms", "covering", "sound", "plain", "silence", "wingless", "distinctive"}:
                return self._clarify(state, "wau_scope", trace, question={"message": message})
        form_context = state.get("last_intent") == "forms" and state.get("entity") == "wau_kikik"
        bare_reason = bool(re.fullmatch(r"(?:and )?why(?: not)?", a["surface"]))
        form_reference = "forms" in c or (form_context and not entities and ("ranking" in c or bare_reason))
        if form_reference and not c & {"people", "role", "launch", "classify", "naming", "covering", "wings", "hummer", "sobek"}:
            if state.get("entity") == "wau_laga" and not entities & {"wau_kikik", "kaca"}:
                return self._profile("laga_forms", state, trace)
            if "ranking" in c and a["explicit_form_reference"]:
                return self._profile("form_comparison_unknown", state, trace)
            if "causal" in c:
                return self._profile("form_reason", state, trace)
        if "appearance" in c and a["ordinal"] is None and not c & {"eddy_comparison", "identity", "head", "tail", "geometry"}:
            if state.get("entity") == "wau_laga":
                return self._profile("laga_forms", state, trace)
            if state.get("entity") == "wau_kikik":
                return self._profile("form_overview", state, trace)
        if "distinctive" in c and not c & {"attack", "competition", "forms", "geometry"}:
            if state.get("entity") == "wau_kikik":
                return self._profile("importance_overview" if "causal" in c else "overview", state, trace)
            return self._clarify(state, "generic", trace)
        if "cultural" in c and "importance" in c:
            return self._profile("cultural_significance", state, trace)
        if "importance" in c and not c & {"speed", "attack", "competition", "skill"}:
            if state.get("entity") == "wau_kikik":
                return self._profile("importance_overview", state, trace)
            return self._clarify(state, "importance_scope", trace)
        if "colour" in c and (entities or state.get("entity") or c & {"forms", "head", "tail", "covering"}):
            return self._profile("colour_unknown", state, trace)
        location = self._location_request(a)
        if state.get("last_intent") == "place_status" and not entities and not c - {"followup", "comparison_followup", "overview"}:
            # A bare geographical follow-up need not repeat the kite name.
            content = set(a["tokens"]) - set(self.rules["generic_stop_tokens"]) - self.router.vocabulary
            if content:
                location = {"requested": True, "places": [" ".join(a["tokens"])], "geography": True}
        if location["requested"] and (entities or state.get("entity")):
            location_profile = self._location_profile(a, state, location)
            if location_profile:
                trace["location_request"] = location
                return self._profile(location_profile, state, trace)
        # A bare multi-context label asks for disambiguation instead of choosing
        # a source section merely because its name occurs in the question.
        specific = c - {"overview", "followup"}
        if "comparison_followup" in c and entities and state.get("last_facet") in {"hummer", "sobek", "wings", "silence", "global_wings", "plain"}:
            profile_id = "laga_features" if "wau_laga" in entities else state["last_facet"]
            return self._profile(profile_id, state, trace)
        if entities == {"wau_laga"} and not specific:
            return self._clarify(state, "laga_scope", trace, ["names", "practice_context"])
        launch_context = state.get("last_intent") == "launch" and state.get("entity") == "wau_laga"
        person_request = bool(c & {"people", "role"})
        if launch_context and "forms" not in c and (
                (person_request and "action" in c) or
                (a["ordinal"] and not (c - {"action", "people", "followup", "comparison_followup", "overview"})
                 and not re.search(r"\b(?:when|year|used|use|old|invent|invented)\b", a["surface"]))):
            trace["selection"] = "launch_role_context"
            return self._profile("launch_roles", state, trace)
        form_context = state.get("last_intent") == "forms" and state.get("entity") == "wau_kikik"
        # Ordinals are not a semantic type by themselves: second person, first
        # launch and third action must not be turned into numbered kite forms.
        form_request = not c & {"origin", "people", "role", "launch"} and (
            "forms" in c or (form_context and (a["ordinal"] is not None or bool(c & {"geometry", "tail", "head", "interpretation"})))
            or (a["ordinal"] is not None and bool(entities & {"wau_kikik", "kaca"}) and bool(c & {"geometry", "tail", "head"})))
        if form_request and not c & {"classify", "covering", "naming", "identity", "wings", "sobek", "hummer", "sound"}:
            if state.get("entity") == "wau_laga" and not entities & {"wau_kikik", "kaca"}:
                return self._profile("laga_forms", state, trace)
            general_forms = a["ordinal"] is None and bool(c & {"count", "form_collection"})
            ordinal = a["ordinal"] or (state.get("form_number") if form_context and not general_forms else None)
            if "interpretation" in c and form_context:
                return self._profile("form_interpretation", state, trace)
            if ("tail" in c or "head" in c) and (form_context or ordinal):
                expected = 2 if "tail" in c else 1
                if not ordinal:
                    return self._clarify(state, "form_number", trace, question={"message": message})
                state["form_number"] = ordinal
                state["requested_component"] = "tail" if "tail" in c else "head"
                if ordinal and ordinal != expected:
                    return self._profile("form_component_unknown", state, trace)
                return self._profile("form_tail" if expected == 2 else "form_head", state, trace)
            if ordinal:
                if not ("forms" in c or form_context or entities & {"wau_kikik", "kaca"}):
                    return self._clarify(state, "form_number", trace)
                return self._profile(f"form_{ordinal}", state, trace, ["form_count"] if "count" in c else [])
            if "forms" in c and "count" not in c and "geometry" not in c:
                return self._profile("form_overview", state, trace)
            if "geometry" in c and "count" not in c:
                return self._clarify(state, "form_number", trace, question={"message": message})
        if ("tail" in c or "head" in c) and not c & {"direction", "control"} and not form_context:
            if state.get("entity") == "wau_laga":
                return self._profile("laga_component_unknown", state, trace)
            return self._clarify(state, "form_number", trace, question={"message": message})
        rankings = self.router.rank(a, state)
        trace["candidates"] = rankings[:5]
        if not rankings or rankings[0]["score"] < self.rules["routing"]["minimum_score"]:
            domain_anchored = bool(entities or set(a["tokens"]) & set(self.rules["domain_tokens"]) or (state.get("entity") and c & {"followup", "forms", "head", "tail", "geometry"}))
            if domain_anchored:
                return self._reply(state, self.catalog["messages"]["unknown"], "clarification", trace=trace)
            return self._reply(state, self.catalog["messages"]["out_of_scope"], "not_documented", "not_documented", trace=trace)
        top = rankings[0]
        facet = top["profile"]
        # Topic confidence is independent of a literal kite keyword. Context,
        # distinctive terms and a matched procedural relation can each anchor it.
        anchored = bool(entities or state.get("last_intent") or set(a["tokens"]) & set(self.rules["domain_tokens"]))
        distinctive = c & set(self.rules.get("standalone_domain_concepts", []))
        procedural = any(set(pattern) <= c for pattern in self.rules.get("standalone_relations", []))
        if not anchored and not distinctive and not procedural:
            return self._clarify(state, "generic", trace)
        # Unknown geometry does not quietly become the familiar shape count.
        if facet == "form_count" and "geometry" in c:
            return self._clarify(state, "form_number", trace, question={"message": message})
        if state.get("entity") == "wau_laga" and not entities & {"wau_kikik", "kaca"}:
            if facet in {"hummer", "sobek", "plain", "wings", "silence", "global_wings"}:
                facet = "laga_features"
            elif facet in {"covering", "paper_weight"}:
                facet = "laga_covering"
        if facet == "height" and state.get("referent") == "launch_distance" and "followup" in c:
            facet = "height_separation"
        # Close scores across unrelated topics request a clarification. Related
        # facets can be specific/general views of the same graph section.
        if len(rankings) > 1 and top["score"] - rankings[1]["score"] < self.rules["routing"]["ambiguity_margin"]:
            second = rankings[1]["profile"]
            if self.profiles[facet]["intent"] != self.profiles[second]["intent"] and not c & {"defence", "legal", "glass", "classify"}:
                trace["selection"] = "ambiguous_scores"
                return self._clarify(state, "generic", trace)
        trace["selected_profile"] = facet
        return self._profile(facet, state, trace)
