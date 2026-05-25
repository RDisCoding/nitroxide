from __future__ import annotations

from itertools import combinations
import sqlite3
from pathlib import Path

from config import GRAPH_PATH, SNAPSHOT_PATH, SQLITE_PATH
from graph_utils import load_graph, save_graph


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


def enrich_relations(graph_path=GRAPH_PATH, snapshot_path=SNAPSHOT_PATH, text_dir=None, bootstrap=False):
    graph = load_graph(graph_path)
    documents = _collect_text_corpus(graph, text_dir=text_dir)

    inferred = []
    extractor_name = "spaCy"

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
