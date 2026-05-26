from __future__ import annotations

import json
import os
from itertools import combinations
import sqlite3
from pathlib import Path

from config import GRAPH_PATH, SNAPSHOT_PATH, SQLITE_PATH
from graph_utils import load_graph, save_graph

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


INFERRED_RELATIONS = {
    "COLLABORATES_WITH",
    "TEAMMATE_OF",
    "SHARES_SKILL",
    "SHARES_PROJECT",
}

TEXT_FIELDS = ("description", "summary", "notes", "content", "text", "body", "bio", "about")


def _node_label(data):
    return data.get("name") or data.get("project_name") or data.get("skill_name") or data.get("label") or data.get("entity")


def _collect_lookup(graph):
    lookup = {
        "employee": {},
        "team": {},
        "project": {},
        "skill": {},
        "department": {},
    }
    for node, data in graph.nodes(data=True):
        entity = data.get("entity")
        label = _node_label(data)
        if entity in lookup and label:
            lookup[entity][label] = node
    return lookup


def _project_employee_map(graph):
    project_to_employees = {}
    for source, target, data in graph.edges(data=True):
        if data.get("relation") == "WORKS_ON":
            source_data = graph.nodes[source]
            target_data = graph.nodes[target]
            if source_data.get("entity") == "employee" and target_data.get("entity") == "project":
                project_to_employees.setdefault(target, []).append(source)
    return project_to_employees


def _employee_project_map(graph):
    employee_to_projects = {}
    for source, target, data in graph.edges(data=True):
        if data.get("relation") == "WORKS_ON":
            source_data = graph.nodes[source]
            target_data = graph.nodes[target]
            if source_data.get("entity") == "employee" and target_data.get("entity") == "project":
                employee_to_projects.setdefault(source, []).append(target)
    return employee_to_projects


def _team_employee_map(graph):
    team_to_employees = {}
    for source, target, data in graph.edges(data=True):
        if data.get("relation") == "MEMBER_OF":
            source_data = graph.nodes[source]
            target_data = graph.nodes[target]
            if source_data.get("entity") == "employee" and target_data.get("entity") == "team":
                team_to_employees.setdefault(target, []).append(source)
    return team_to_employees


def _skill_employee_map(graph):
    skill_to_employees = {}
    for source, target, data in graph.edges(data=True):
        if data.get("relation") == "HAS_SKILL":
            source_data = graph.nodes[source]
            target_data = graph.nodes[target]
            if source_data.get("entity") == "employee" and target_data.get("entity") == "skill":
                skill_to_employees.setdefault(target, []).append(source)
    return skill_to_employees


def _collect_text_corpus(graph, text_dir=None):
    documents = []

    for node, data in graph.nodes(data=True):
        parts = []
        for field in TEXT_FIELDS:
            value = data.get(field)
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
        if parts:
            documents.append((f"graph-node:{node}", "\n".join(parts)))

    if text_dir:
        root = Path(text_dir)
        if root.exists():
            for path in root.rglob("*"):
                if path.is_file() and path.suffix.lower() in {".txt", ".md", ".rst"}:
                    try:
                        documents.append((str(path), path.read_text(encoding="utf-8")))
                    except Exception:
                        continue

    return documents


def _node_text(graph, node):
    data = graph.nodes[node]
    for field in TEXT_FIELDS:
        value = data.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return build_fallback_description(graph, node)


def build_fallback_description(graph, node):
    data = graph.nodes[node]
    entity = data.get("entity") or str(node).split(":", 1)[0]
    label = _node_label(data)
    if label == "node" and isinstance(node, str):
        label = node

    if entity == "employee":
        parts = [f"{label} is an employee."]
        if data.get("role"):
            parts.append(f"Role: {data['role']}.")
        return " ".join(parts)
    if entity == "team":
        return f"{label} is a team."
    if entity == "department":
        return f"{label} is a department."
    if entity == "project":
        return f"{label} is a project."
    if entity == "skill":
        return f"{label} is a skill."
    return f"{label} is a {entity or 'node'}."


def _make_node_records(graph):
    records = []
    for node, data in graph.nodes(data=True):
        payload = {
            key: value
            for key, value in data.items()
            if key not in {"entity", "label"}
        }
        records.append(
            {
                "node_id": node,
                "entity": data.get("entity"),
                "label": _node_label(data),
                **payload,
            }
        )
    return records


def _make_relation_candidates(graph):
    candidates = []
    for node, data in graph.nodes(data=True):
        if data.get("entity") != "employee":
            continue
        candidates.append(
            {
                "node_id": node,
                "entity": data.get("entity"),
                "label": data.get("label"),
                **{k: v for k, v in data.items() if k not in {"entity", "label", "description"}},
            }
        )
    return candidates


def _load_groq_client():
    try:
        from groq import Groq
    except Exception as exc:
        raise RuntimeError("Groq SDK is not installed. Install the 'groq' package first.") from exc

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GROQ_API_KEY. Put it in the .env file or environment.")
    return Groq(api_key=api_key)


def _clean_json_text(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


def _parse_llm_output(text):
    text = _clean_json_text(text)

    try:
        payload = json.loads(text)
    except Exception:
        # Attempt to recover a JSON array/object from noisy LLM output by
        # extracting the first balanced JSON block (array or object).
        def _find_matching(text, start_idx, open_ch, close_ch):
            depth = 0
            for i in range(start_idx, len(text)):
                ch = text[i]
                if ch == open_ch:
                    depth += 1
                elif ch == close_ch:
                    depth -= 1
                    if depth == 0:
                        return i
            return -1

        payload = None
        # Try to find an array first
        start = text.find("[")
        if start != -1:
            end = _find_matching(text, start, "[", "]")
            if end != -1:
                snippet = text[start:end + 1]
                try:
                    payload = json.loads(snippet)
                except Exception:
                    payload = None

        # If no array, try an object
        if payload is None:
            start = text.find("{")
            if start != -1:
                end = _find_matching(text, start, "{", "}")
                if end != -1:
                    snippet = text[start:end + 1]
                    try:
                        payload = json.loads(snippet)
                    except Exception:
                        payload = None

        if payload is None:
            raise ValueError("Unable to parse LLM output as JSON; received: %r" % (text[:200],))

    if isinstance(payload, dict):
        payload = payload.get("relations", payload.get("items", []))
    if not isinstance(payload, list):
        raise ValueError("LLM output must be a JSON list of relations.")
    return payload


def _chunk_records(records, max_records=8):
    for index in range(0, len(records), max_records):
        yield records[index:index + max_records]


def _llm_extract(graph, documents, model=None, include_text=False, node_only=False):
    client = _load_groq_client()
    model_name = model or os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

    if node_only:
        records = _make_relation_candidates(graph)
    else:
        records = _make_node_records(graph)

    node_blob = json.dumps(records, ensure_ascii=False, separators=(",", ":"))

    doc_lines = []
    if include_text:
        for source, text in documents:
            snippet = " ".join(text.split())
            if len(snippet) > 1200:
                snippet = snippet[:1200] + "..."
            doc_lines.append(f"SOURCE: {source}\nTEXT: {snippet}")

    system_prompt = (
        "You are a relation extraction engine. "
        "Infer relations only from the provided node data. "
        "If extra text sources are present, use them as supporting evidence only. "
        "Return a JSON array only. Each item must contain source_node, target_node, relation, evidence, confidence. "
        "Only use node_id values that appear in the node list. "
        "Do not invent nodes. Prefer relations that are explicitly supported by the text. "
        "Only emit one of these relation types: COLLABORATES_WITH, TEAMMATE_OF, SHARES_SKILL, SHARES_PROJECT."
    )
    inferred = []
    seen = set()
    allowed_nodes = {item["node_id"] for item in records}

    for batch in _chunk_records(records, max_records=6 if node_only else 10):
        batch_blob = json.dumps(batch, ensure_ascii=False, separators=(",", ":"))
        user_prompt = (
            "NODE DATA JSON:\n"
            + batch_blob
            + ("\n\nTEXT SOURCES:\n" + "\n\n".join(doc_lines) if doc_lines and not node_only else "")
            + "\n\nReturn JSON only."
        )

        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
            max_tokens=2000,
        )

        content = response.choices[0].message.content or "[]"
        parsed = _parse_llm_output(content)

        for item in parsed:
            source = item.get("source_node")
            target = item.get("target_node")
            relation = item.get("relation")
            evidence = item.get("evidence") or ""
            if not source or not target or not relation:
                continue
            if source not in allowed_nodes or target not in allowed_nodes:
                continue
            relation = str(relation).upper().strip()
            if relation not in INFERRED_RELATIONS:
                continue
            key = (source, target, relation)
            if key in seen:
                continue
            seen.add(key)
            inferred.append((source, target, relation, evidence or f"LLM inferred {relation}"))

    return inferred


def _build_sentences(graph):
    sentences = []

    for project_node, employees in _project_employee_map(graph).items():
        if len(employees) < 2:
            continue
        employee_names = ", ".join(_node_label(graph.nodes[node]) for node in employees)
        project_name = _node_label(graph.nodes[project_node])
        sentences.append(("COLLABORATES_WITH", employee_names, project_name, f"{employee_names} collaborate on {project_name}."))

    for team_node, employees in _team_employee_map(graph).items():
        if len(employees) < 2:
            continue
        employee_names = ", ".join(_node_label(graph.nodes[node]) for node in employees)
        team_name = _node_label(graph.nodes[team_node])
        sentences.append(("TEAMMATE_OF", employee_names, team_name, f"{employee_names} are teammates in {team_name}."))

    for skill_node, employees in _skill_employee_map(graph).items():
        if len(employees) < 2:
            continue
        employee_names = ", ".join(_node_label(graph.nodes[node]) for node in employees)
        skill_name = _node_label(graph.nodes[skill_node])
        sentences.append(("SHARES_SKILL", employee_names, skill_name, f"{employee_names} share the skill {skill_name}."))

    for project_node, employees in _project_employee_map(graph).items():
        if len(employees) < 2:
            continue
        employee_names = ", ".join(_node_label(graph.nodes[node]) for node in employees)
        project_name = _node_label(graph.nodes[project_node])
        sentences.append(("SHARES_PROJECT", employee_names, project_name, f"{employee_names} share the project {project_name}."))

    return sentences


def _load_spacy_pipeline():
    import spacy

    try:
        nlp = spacy.load("en_core_web_sm")
    except Exception:
        nlp = spacy.blank("en")
        nlp.add_pipe("sentencizer")
    if "entity_ruler" not in nlp.pipe_names:
        if "ner" in nlp.pipe_names:
            nlp.add_pipe("entity_ruler", before="ner")
        else:
            nlp.add_pipe("entity_ruler")
    return nlp


def _build_entity_patterns(graph):
    patterns = []
    for node, data in graph.nodes(data=True):
        label = _node_label(data)
        entity = data.get("entity")
        if label and entity:
            patterns.append({"label": entity.upper(), "pattern": label})
    return patterns


def _sentence_relations(doc, lookup):
    sentence_text = doc.text.strip()
    lower_text = sentence_text.lower()
    entities = {}
    for ent in doc.ents:
        entities.setdefault(ent.label_.lower(), []).append(ent.text)

    employee_nodes = [lookup["employee"][text] for text in entities.get("employee", []) if text in lookup["employee"]]
    team_nodes = [lookup["team"][text] for text in entities.get("team", []) if text in lookup["team"]]
    project_nodes = [lookup["project"][text] for text in entities.get("project", []) if text in lookup["project"]]
    skill_nodes = [lookup["skill"][text] for text in entities.get("skill", []) if text in lookup["skill"]]

    relations = []

    collaborate_cues = {"collaborate", "collaborates", "collaboration", "work with", "worked with", "partner", "partnered", "coordinate", "coordinated"}
    team_cues = {"teammate", "teammates", "team", "alongside", "together"}
    skill_cues = {"skill", "skills", "expert", "expertise", "proficient", "proficiency", "familiar", "specialize", "specialized"}
    project_cues = {"project", "projects", "initiative", "platform", "product", "program", "build", "built", "deliver", "delivered", "ship", "shipped", "work on", "worked on"}

    verb_lemmas = {token.lemma_.lower() for token in doc if token.pos_ in {"VERB", "AUX"}}

    if len(employee_nodes) >= 2 and any(cue in lower_text for cue in collaborate_cues | team_cues):
        if collaborate_cues & set(lower_text.split()) or any(lemma in {"collaborate", "work", "partner", "coordinate"} for lemma in verb_lemmas) or "work with" in lower_text:
            relations.append(("COLLABORATES_WITH", employee_nodes, project_nodes or team_nodes or skill_nodes, sentence_text))

    if len(employee_nodes) >= 2 and any(cue in lower_text for cue in team_cues):
        relations.append(("TEAMMATE_OF", employee_nodes, team_nodes, sentence_text))

    if len(employee_nodes) >= 2 and any(cue in lower_text for cue in skill_cues) and skill_nodes:
        relations.append(("SHARES_SKILL", employee_nodes, skill_nodes, sentence_text))

    if len(employee_nodes) >= 2 and any(cue in lower_text for cue in project_cues) and project_nodes:
        relations.append(("SHARES_PROJECT", employee_nodes, project_nodes, sentence_text))

    if len(employee_nodes) >= 1 and project_nodes and any(cue in lower_text for cue in {"work on", "worked on", "building", "built", "own", "owns", "owned"} | project_cues):
        relations.append(("WORKS_ON", employee_nodes, project_nodes, sentence_text))

    return relations


def _spacy_extract(graph, documents):
    nlp = _load_spacy_pipeline()
    ruler = nlp.get_pipe("entity_ruler")
    ruler.add_patterns(_build_entity_patterns(graph))

    lookup = _collect_lookup(graph)
    inferred = []
    seen = set()

    for _source, text in documents:
        doc = nlp(text)
        for sent in doc.sents:
            for relation, source_nodes, target_nodes, evidence in _sentence_relations(sent, lookup):
                source_nodes = sorted(set(source_nodes))
                target_nodes = sorted(set(target_nodes))

                if relation in {"COLLABORATES_WITH", "TEAMMATE_OF", "SHARES_SKILL", "SHARES_PROJECT"} and len(source_nodes) >= 2:
                    for left, right in combinations(source_nodes, 2):
                        key = (left, right, relation)
                        if key not in seen:
                            inferred.append((left, right, relation, evidence))
                            seen.add(key)

                if relation == "WORKS_ON" and source_nodes and target_nodes:
                    for source_node in source_nodes:
                        for target_node in target_nodes:
                            key = (source_node, target_node, relation)
                            if key not in seen:
                                inferred.append((source_node, target_node, relation, evidence))
                                seen.add(key)

    return inferred


def _fallback_extract(graph, sentences):
    inferred = []
    seen = set()

    for relation, employee_text, topic_text, sentence in sentences:
        employee_names = [part.strip() for part in employee_text.split(",") if part.strip()]
        if len(employee_names) < 2:
            continue

        lookup = _collect_lookup(graph)
        employee_nodes = [lookup["employee"][name] for name in employee_names if name in lookup["employee"]]
        for left, right in combinations(sorted(set(employee_nodes)), 2):
            key = (left, right, relation)
            if key not in seen:
                inferred.append((left, right, relation, sentence))
                seen.add(key)

    return inferred


def _dedupe_existing_graph_edges(graph):
    inferred = []
    seen = set()

    for source, target, data in graph.edges(data=True):
        relation = data.get("relation")
        evidence = data.get("evidence")
        extracted_by = data.get("extracted_by")
        if relation not in INFERRED_RELATIONS or not evidence:
            continue
        key = (source, target, relation)
        if key in seen:
            continue
        seen.add(key)
        inferred.append((source, target, relation, evidence, extracted_by or "spaCy"))

    return inferred


def enrich_relations(graph_path=GRAPH_PATH, snapshot_path=SNAPSHOT_PATH, text_dir=None, mode="spacy", bootstrap=False, llm_model=None, node_only=False):
    graph = load_graph(graph_path)
    documents = _collect_text_corpus(graph, text_dir=text_dir)

    inferred = []
    extractor_name = mode

    if mode == "llm":
        if not documents and not node_only:
            print("No free-text sources found on nodes or in the optional text directory.")
        inferred = _llm_extract(graph, documents, model=llm_model, include_text=not node_only, node_only=node_only)
        extractor_name = "llm"
    else:
        if documents:
            try:
                inferred = _spacy_extract(graph, documents)
            except Exception as exc:
                print(f"spaCy extraction failed; using fallback bootstrap mode ({exc.__class__.__name__}).")
                inferred = _fallback_extract(graph, _build_sentences(graph)) if bootstrap else []
                extractor_name = "fallback"
        else:
            print("No free-text sources found on nodes or in the optional text directory.")
            if bootstrap:
                inferred = _fallback_extract(graph, _build_sentences(graph))
                extractor_name = "fallback"

    existing_inferred = _dedupe_existing_graph_edges(graph)
    inferred.extend((source, target, relation, evidence) for source, target, relation, evidence, _by in existing_inferred)

    deduped = {}
    for source, target, relation, evidence in inferred:
        deduped[(source, target, relation)] = (source, target, relation, evidence)

    inferred = list(deduped.values())

    for source, target, relation, evidence in inferred:
        graph.add_edge(source, target, relation=relation, evidence=evidence, extracted_by=extractor_name)

    conn = sqlite3.connect(SQLITE_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS inferred_relations (
                source_node TEXT NOT NULL,
                target_node TEXT NOT NULL,
                relation    TEXT NOT NULL,
                evidence    TEXT NOT NULL,
                PRIMARY KEY (source_node, target_node, relation)
            )
            """
        )
        cur.execute("DELETE FROM inferred_relations")
        cur.executemany(
            "INSERT INTO inferred_relations (source_node, target_node, relation, evidence) VALUES (?,?,?,?)",
            [(source, target, relation, evidence) for source, target, relation, evidence in inferred],
        )
        conn.commit()
    finally:
        conn.close()

    save_graph(graph, graph_path)
    save_graph(graph, snapshot_path)

    print(f"Extracted {len(inferred)} inferred relations using {extractor_name}")
    for source, target, relation, evidence in inferred[:10]:
        print(f"  {relation}: {source} -> {target}")
        print(f"    evidence: {evidence}")

    return inferred


if __name__ == "__main__":
    enrich_relations()
