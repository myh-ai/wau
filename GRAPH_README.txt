WAUTRACE SEMANTIC NETWORK

The semantic network is the sole representation of cultural knowledge used by
WauTrace. Source checking, author approval of operational assertions, chatbot
performance and participant-study approval are separate matters. The network
is available for prototype inspection; its 74 operational edges await explicit
author review in reviews/operational_claim_review.html.

INPUTS AND COUNTS
knowledge.json: 36 source-linked records, 74 typed triples, 59 evidence entries.
WauTrace_Network_Template.json: 83 nodes, 74 assertion edges, 73 semantic fact
groups. The nodes comprise 82 assertion endpoints and one isolated Kemetek
candidate. Twelve factual intents and one not-documented fallback support
retrieval. Every assertion keeps its scope, evidence state, source excerpt,
polarity and pending author-review decision.

PUBLICATION FIGURE
Use graphs/publication_semantic_network.png, .pdf or .svg.
This selected view contains 18 distinct nodes and 18 edges. It does not replace
the full network. The PNG is 2100 pixels wide at 300 dpi for a 7-inch figure;
PDF and SVG retain vector text and lines. Record IDs, printed pages and source
quotations appear in publication_edge_sources.json and .csv, outside the drawing.
The mapping includes each selected relation's operational E### edge ID.
Caption: graphs/publication_graph_caption.txt.
Rendering metadata: graphs/publication_graph_manifest.json.

COMPLETE EXPORTS
All formats preserve every operational node and assertion edge, including all
metadata. None creates an approval or drops a pending review field.

- full_graph.json: complete nodes and edges; other network fields are retained
  under metadata.network_metadata.
- full_graph_edges.csv: every edge field is a column; structured values use
  JSON. edge_json preserves the exact complete row. UTF-8 with BOM.
- full_graph.graphml: original IDs and endpoints; structured attributes use
  JSON. node_json and edge_json preserve complete records and value types.
- full_graph.dot: directed edges, explicit NOT labels and dashed source-variance
  edges. JSON attributes preserve the complete graph data.
- export_manifest.json: computed counts, format descriptions and checksums.

REBUILD AND CHECK
Run from the extracted package folder. Use py on Windows or python3 on Linux
and macOS. All default paths resolve from the scripts' folder.

  py validate_knowledge.py
  py knowledge_regression_checks.py
  py build_graph.py
  py build_publication_graph.py
  py test_export_graph.py --report graph_export_report.json

build_graph.py checks the record/triple correspondence and exports the complete
graph. export_graph.py exports the graph directly. The publication script
requires Inkscape for PDF/PNG rendering; included figures can be opened without
installing it. Other export/check scripts use Python's standard library.
Graphviz is used for an optional DOT syntax check if installed.

Optional image checksum check:
  py validate_knowledge.py --source-root path/to/source_images

Optional custom output:
  py export_graph.py --output other_graphs

INTERPRETATION
Laga's p.73 heading label and p.144 named-type classification have separate
source scopes. No global identity or disjointness is asserted. S11 describes
the competitive purpose of the coated string; S12/E077 describes the source's
non-universal class statement about leaf-shaped wings. Most does not mean all.
Direct Kikik exclusions govern Kikik's feature answers; an undocumented Laga
feature does not become true through class inheritance. Melaka status belongs
to the 2002 source. Kemetek has no asserted edge. Form 2/Form 3 source-language
wording remains in the evidence table and operational records. Two-player role
labels do not imply four people or undocumented synonym pairs. Duplicate
representations of the defence action retain one displayed answer with their
combined source references.

CHECK LIMITS
knowledge_validation_report.json checks source links, schema, IDs, polarity,
counts and review-state consistency. validation_report.json checks complete
record-to-edge correspondence. knowledge_regression_report.json checks source
scopes and graph-answer contracts. graph_export_report.json reports eight
lossless export tests. These are development and data-integrity checks, not an
independent RQ2 accuracy result, cultural-expert validation or study approval.
