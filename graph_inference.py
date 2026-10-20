"""Source-bound feature resolution over WauTrace's semantic network.

This helper resolves source-checked graph assertions and preserves their
qualifiers, source evidence and operational review metadata.
"""
from __future__ import annotations


def deduplicate_answers(edges):
    """Return one answer per explicitly curated semantic fact.

    The graph keeps every source-linked triple. Only the answer presentation is
    deduplicated. Different polarities, statuses, subjects, relations or source
    identifiers never merge, even if a semantic_fact_id was reused by mistake.
    Unlabelled edges remain separate. This helper performs no fuzzy matching.
    """
    groups = {}
    for edge in edges:
        identity = edge.get("semantic_fact_id") or ("edge", edge["edge_id"])
        key = (identity, edge.get("subject"), edge.get("relation"),
               edge.get("polarity"), edge.get("status"),
               tuple(sorted({q.get("source_id") for q in edge.get("evidence", [])})))
        groups.setdefault(key, []).append(edge)
    answers = []
    for group in groups.values():
        group = sorted(group, key=lambda edge: edge["edge_id"])
        by_id = {edge["edge_id"]: edge for edge in group}
        preferred = [edge.get("canonical_answer_edge_id") for edge in group]
        preferred = [eid for eid in preferred if eid in by_id]
        # A curated canonical edge supplies the full conditional answer; the
        # deterministic fallback only controls order and never rewrites text.
        chosen_id = sorted(set(preferred))[0] if preferred else sorted(by_id)[0]
        chosen = by_id[chosen_id]
        evidence, seen = [], set()
        for edge in group:
            for quote in edge.get("evidence", []):
                qkey = (quote.get("source_id"), quote.get("page"),
                        quote.get("language"), quote.get("quote"))
                if qkey not in seen:
                    seen.add(qkey)
                    evidence.append(dict(quote))
        answers.append({
            "semantic_fact_id": chosen.get("semantic_fact_id"),
            "canonical_answer_edge_id": chosen_id,
            "answer_en": chosen.get("answer_en"),
            "status": chosen.get("status"),
            "source_edge_ids": sorted(by_id),
            "record_ids": sorted({edge["record_id"] for edge in group}),
            "scopes": sorted({edge["scope"] for edge in group}),
            "scope_notes": list(dict.fromkeys(edge["scope_note"] for edge in group)),
            "required_context_edge_ids": sorted({eid for edge in group
                for eid in edge.get("required_context_edge_ids", []) if eid not in by_id}),
            "evidence": evidence,
        })
    return sorted(answers, key=lambda answer: answer["canonical_answer_edge_id"])


def resolve_feature(network, subject, feature, source_id="S01"):
    """Prefer direct feature evidence; keep class-most statements contextual.

    Opposing direct statements return source_variance. A class statement with
    quantifier 'most' never establishes a feature on an undocumented subtype.
    Edge IDs and original evidence are returned for traceable source cards.
    """
    edges = [e for e in network.get("edges", [])
             if any(q.get("source_id") == source_id for q in e.get("evidence", []))]
    direct = [e for e in edges if e.get("subject") == subject
              and e.get("relation") == "has_feature"
              and e.get("object_value") == feature]
    positive = [e for e in direct if e.get("polarity") == "positive"]
    negative = [e for e in direct if e.get("polarity") == "negative"]

    # Collect class membership using visited nodes: cycles cannot recurse forever.
    classes, membership, frontier = set(), [], [subject]
    visited = set()
    while frontier:
        current = frontier.pop()
        if current in visited:
            continue
        visited.add(current)
        for edge in edges:
            if (edge.get("subject") == current and edge.get("relation") == "is_a"
                    and edge.get("object_type") == "entity" and edge.get("polarity") == "positive"):
                parent = edge["object_value"]
                classes.add(parent)
                membership.append(edge)
                frontier.append(parent)
    def qualified(edge):
        return (edge.get("relation") == "most_have" and edge.get("object_value") == feature
                and edge.get("polarity") == "positive" and edge.get("quantifier") == "most"
                and edge.get("inheritance") == "context_only")
    class_direct = [e for e in edges if e.get("subject") == subject and qualified(e)]
    context = [e for e in edges if e.get("subject") in classes and qualified(e)]

    result = {"subject": subject, "feature": feature, "source_id": source_id,
              "status": "not_documented", "value": None, "quantifier": None,
              "source_edge_ids": [], "class_context_edge_ids": [e["edge_id"] for e in context],
              "membership_edge_ids": list(dict.fromkeys(e["edge_id"] for e in membership)),
              "inherited_as_subtype_fact": False, "evidence": [],
              "class_candidate_action": "context_only_not_inherited" if context else "none"}
    selected = []
    if positive and negative:
        selected = positive + negative
        result.update(status="source_variance", reason="Opposing direct source statements require explicit reporting; neither is silently discarded.")
    elif negative:
        selected = negative
        result.update(status="explicit_negative", value=False,
                      reason="Direct subtype evidence explicitly excludes the feature.",
                      class_candidate_action="overridden_for_subtype_answer" if context else "none")
    elif positive:
        selected = positive
        result.update(status="supported", value=True,
                      reason="Direct subtype evidence establishes the feature; class frequency is not its basis.",
                      class_candidate_action="direct_subtype_evidence_has_priority" if context else "none")
    elif class_direct:
        selected = class_direct
        result.update(status="supported", value="qualified_class_statement", quantifier="most",
                      reason="The source directly describes most members of this class; it does not describe every member.")
    else:
        result["reason"] = ("No direct subtype feature statement is documented. The class-most statement is context, not positive subtype evidence."
                            if context else "No source-bound feature statement is documented for this query.")
    result["source_edge_ids"] = [e["edge_id"] for e in selected]
    seen = set()
    for edge in selected + context + membership:
        for quote in edge.get("evidence", []):
            key = (quote.get("source_id"), quote.get("page"), quote.get("language"), quote.get("quote"))
            if key not in seen:
                seen.add(key)
                result["evidence"].append({k: quote[k] for k in ["source_id", "page", "language", "quote"]})
    return result
