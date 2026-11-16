# MEMORY CENTER / KNOWLEDGE GRAPH — RESEARCH REVIEW
**Research only, per instruction. No code, no schema, no build.**

---

## 1. RESEARCH FINDINGS — would a visual Memory Center provide genuine value, or duplicate existing screens?

**Genuine value exists, but it's narrower and later than the framing in the prompt suggests.** Every current Mission Control screen answers "what is the state of X right now" (Health Center, Warehouse Command Center, Cost Intelligence Center) or "what happened in this one evaluation" (the enriched inspector panel). None of them answer **"why does X exist, and what does it connect to"** — a genuinely different question shape, spanning multiple evaluations/rules/decisions at once rather than drilling into one. That's a real, unfilled gap, not a duplicate.

**The honest caveat: the gap is filled by data that doesn't exist yet.** Every high-value question in Section 8 below ("why does Dataset B exist," "why was Rule 24 investigated") resolves to `decision_records`/`investigation_records` — tables that are only now being authorized, not yet populated at any real depth. A graph visualization over an empty or thinly-populated table is a UI ahead of its data. This is the single biggest factor in the GO/GO LATER/NO-GO call at the end.

---

## 2. NODE TYPES

Recommended, and specifically *not* recommended, based on what maps to real Apex entities:

| Node type | Recommend? | Why |
|---|---|---|
| Decisions (`decision_records`) | **Yes** | The core "why" node — everything else connects back to a decision |
| Investigations (`investigation_records`) | **Yes** | The core "what did we find" node |
| Rules | **Yes** | Already named entities (`Rule 24`, `Rule 30`) with real activation history in `rule_activations` |
| Datasets (A, B) | **Yes, but as a small, fixed set** — 2 nodes, not a category that grows |
| Systems/Components (ATE, Mission Control, Cost Intelligence) | **Yes, but equally small and fixed** — these are architectural landmarks, not a growing node type |
| Bug fixes | **Fold into Investigations** — a bug fix is the *conclusion* of an investigation, not a separate node type; splitting them duplicates the same event |
| Features | **No, for now** — too vague a category to have real edges; a "feature" is usually just a decision plus the code that implements it, already covered |
| Models (future LightGBM/XGBoost) | **Not yet** — no real data until those exist; premature to add empty node types |
| Cost Intelligence, ATE (as concepts) | **Represent as Systems, not a separate category** — see above |

**Net: 4 real node types for V1 — Decision, Investigation, Rule, System** (the last one covering both datasets and components, since neither grows fast enough to need its own category).

---

## 3. EDGE TYPES

| Edge | Recommend? | Why |
|---|---|---|
| `INVESTIGATED_BY` (Rule/System → Investigation) | **Yes** | Directly answers "why was Rule 24 investigated" |
| `LED_TO` (Investigation → Decision) | **Yes** | Directly answers "what led to ATE" — an investigation's finding producing a decision is the single most common real pattern in this project's own history (the fallback-bug investigation leading to the fix decision, the archive-verification investigation leading to the checkpoint_stamps decision) |
| `DEPENDS_ON` (System → System, or Decision → System) | **Yes** | Answers "what would be affected if I changed ATE" |
| `SUPERSEDES` (Decision → Decision) | **Yes, but rare** | Real cases exist (v7.9.5 → v7.9.8 rule changes) but this should be sparse, not a default on every decision |
| `RELATES_TO` | **No — reject as a default edge type** | A catch-all relationship with no directional meaning is the one thing that turns a knowledge graph into an unreadable hairball. Every real relationship in this project's own history has a *direction and a reason* (X caused Y, X depends on Y, X was investigated because of Y) — force every edge to be one of the specific types above, and if nothing specific fits, that's a sign the connection isn't real enough to graph yet. |
| `CREATED_BY` | **No, for V1** | Every decision/investigation already has one author (you). A field, not an edge — doesn't need graph traversal. |
| `USES` / `REFERENCES` | **Fold into `DEPENDS_ON`** | The distinction between "uses" and "depends on" isn't load-bearing for any of the Section 8 questions; one edge type covers both without losing real information. |

**Net: 4 edge types — `INVESTIGATED_BY`, `LED_TO`, `DEPENDS_ON`, `SUPERSEDES`.** Deliberately smaller than the prompt's example list — a knowledge graph with 7 loosely-defined edge types is harder to populate consistently and harder to read than one with 4 sharp ones.

---

## 4. DECISION_RECORDS / INVESTIGATION_RECORDS AS THE GRAPH FOUNDATION

**Yes, unambiguously — there's no real alternative.** These two tables (now being built per the Command Chat authorization) are the only place in Apex where "why" is recorded as a discrete, dated fact rather than implied by a code diff or a Discord message. A knowledge graph without them would have nothing to be a graph *of*. This also means the graph's real build sequence is downstream of Command Chat's Phase 1/2, not a parallel effort — reinforcing the GO LATER framing below.

---

## 5. OPEN-SOURCE GRAPH LIBRARIES — researched current (2026) landscape, not assumed

| Library | Pros | Cons | Mission Control compatibility | Maintenance burden |
|---|---|---|---|---|
| **Cytoscape.js** | Purpose-built for graph *analysis*, not just diagramming — built-in layouts (breadthfirst, concentric, force-directed), works framework-free, loadable directly from a CDN, ~500K weekly downloads, actively maintained through 2026 | Steeper API than a pure-React tool if you ever migrate to React; DOM-based rendering has real limits on very large graphs (not a concern at Apex's node counts) | **High** — Mission Control is vanilla JS/HTML with no build step (confirmed: `PAGE` is a raw HTML/JS string, scripts loaded via CDN per the existing convention). Cytoscape.js needs no framework and no bundler — a direct fit. | Low — mature, stable API, no framework-version treadmill to track |
| **React Flow** | Excellent for workflow/diagram *authoring* tools with editable, stateful nodes | **Requires React.** Mission Control has no React dependency anywhere in the current codebase — adopting it here means introducing an entire framework for one screen. Also fundamentally the wrong tool for this job: current research (2026) is consistent that React Flow is built for *authoring* (workflow builders, editable diagrams), while Apex's need is *analysis* (exploring existing relationships) — the wrong primitive even setting the framework mismatch aside. | **Low** | High relative to the alternative — a new framework dependency for one feature |
| **Sigma.js** | WebGL rendering, handles very large graphs (100K+ nodes) | Requires a separate graph-data library (graphology) alongside it — two dependencies, not one; its performance advantage is aimed at graph sizes Apex won't approach for years (a few hundred decisions/investigations/rules, not tens of thousands) | Medium | Medium — two libraries to track instead of one, for a scale problem Apex doesn't have |
| **D3 Force Graph** | Maximum customization, no dependency beyond D3 itself | Steepest learning curve of the group; every layout/interaction behavior has to be hand-built rather than configured | Medium | Medium-high — more custom code to maintain long-term |

**Recommendation: Cytoscape.js.** It's the only option that fits Mission Control's actual stack (framework-free, CDN-loadable) without a compromise, and its purpose (graph *analysis*) matches Apex's actual need (exploring existing relationships) rather than React Flow's purpose (authoring new ones). Sigma.js's performance advantage solves a scale problem Apex doesn't have; D3 solves nothing Cytoscape.js doesn't already solve with less custom code.

---

## 6. WHERE SHOULD THIS LIVE — Option A/B/C

**Recommend Option A — standalone Memory Center screen — not embedded in Command Chat.** Reasoning: a graph is a spatial, browseable artifact you look *at* — clicking, panning, following an edge to see what it connects to. That's a fundamentally different interaction than a conversational Q&A stream. Embedding a graph inside a chat interface (Option B) would mean building two different interaction paradigms inside one screen, which is exactly the "duplicate/fragment visibility" pattern Mission Control has avoided everywhere else. A standalone screen, consistent with how Cost Intelligence Center was added, is the right shape — with Command Chat able to **link into** specific nodes (a decision, an investigation) the same way `openEval()` already links into the evaluation inspector panel, rather than the graph living inside the chat itself.

---

## 7. NAMING

**Recommend "Memory Center."** Not "Knowledge Graph" (describes the implementation, not the purpose — matches the pattern of avoiding technology-named screens throughout Mission Control, e.g. "Warehouse Command Center" not "SQLite Dashboard"). Not "Decision Intelligence Center" (too narrow — excludes investigations, rules, and systems, which are real node types). Not "Investigation Center" (same problem, narrower still). "Memory Center" matches the plain-language naming convention already used everywhere else in Mission Control's nav (Health Center, Learning Center, Validation) and describes the *purpose* — this is where Apex's institutional memory lives — not the underlying graph-library implementation detail.

---

## 8. HIGH-VALUE USE CASES — which questions a graph answers better than existing screens

| Question | Graph advantage over existing screens |
|---|---|
| "What led to ATE?" | A traversal (`Investigation --LED_TO--> Decision --LED_TO--> Decision...`) shows the *chain*, not just an endpoint — no existing screen shows causal chains, only individual records |
| "What depends on Rule 30?" | `DEPENDS_ON` edges answer this directly; the equivalent today would mean manually re-reading every investigation/decision text for "Rule 30" mentions |
| "What systems would be affected if I changed ATE?" | This is a **blast-radius question** — explicitly the same shape as the standalone CodeFlow tool's job (from the earlier architecture review), just at the *decision/system* level instead of the *code file* level. Worth noting: this is genuinely CodeFlow's territory extended one level up, not a new capability invented from scratch. |
| "Why does Dataset B exist?" / "Why was Rule 24 investigated?" | Single-node lookup — a graph isn't strictly *necessary* here, a direct `search_decisions()`/`search_investigations()` call (already in Command Chat's Phase 3/4 scope) answers this exactly as well. **This is an important, honest distinction**: several of the prompt's own example questions don't actually need a graph at all — they need the underlying tables to exist and be searchable, which Command Chat already provides. The graph's *real* differentiator is multi-hop traversal (chains, blast radius), not single-record lookup. |

---

## 9. COMMAND CHAT INTEGRATION

**Could Command Chat query the graph? Yes, meaningfully — but only for the multi-hop questions, not the single-lookup ones.** "Why was Rule 24 investigated" is answered by `search_investigations()` alone (Phase 3/4, no graph needed). "What would be affected if I changed ATE" genuinely benefits from a graph traversal Command Chat could run and describe in prose ("ATE depends on: Dataset A (read), Mission Control (integration). 3 decisions reference ATE directly."). This is real, additive value, not unnecessary complexity — **but it's an integration to add *after* the graph and Command Chat both exist independently**, not a reason to build them coupled together from the start.

---

## 10. BUILD COMPLEXITY ESTIMATE

Low-to-moderate, and heavily front-loaded on *data*, not code: one new SQLite table (`graph_edges` — `edge_id, source_type, source_id, edge_type, target_type, target_id, created_at`, trivially small), a thin query layer over it plus the existing `decision_records`/`investigation_records`/rules corpus (nodes), Cytoscape.js loaded via CDN with data fed in as a JSON node/edge list, and one new Mission Control screen following the exact pattern already used twice this session (nav link, container, route, render function). The actual visualization code is a day of focused work once the library choice is made. **The real cost isn't the build — it's populating `graph_edges` with real, meaningful relationships**, which requires `decision_records`/`investigation_records` to exist and have real content first.

---

## 11. GO / GO LATER / NO-GO

**GO LATER.** Not NO-GO — the research findings above are genuinely positive: real gap, real node/edge model, a library choice that fits the stack with no compromise, low build complexity. But it's sequenced *after* Command Chat's Phase 1/2 (`decision_records`/`investigation_records` existing and populated), for a reason stated plainly rather than as a formality: **a knowledge graph is a visualization of data that doesn't exist yet.** Building the graph screen before those tables have real content would produce an impressive-looking, nearly-empty graph — exactly the kind of premature infrastructure Principle 2 ("infrastructure must earn its place") exists to catch.

**Recommended trigger to revisit as GO**: once `decision_records`/`investigation_records` have accumulated roughly 15–20 real entries each (enough for a graph to show genuine structure, not a handful of isolated dots) — a natural checkpoint to reach given Phase 1/2 of Command Chat backfills several entries immediately and more accrue as the project continues.

---

## IF/WHEN THIS BECOMES GO — PHASED ROADMAP (for the record, not authorized now)

```
Phase 1 — graph_edges table (one new table, ~5 columns) + manual edge
           entry for the backfilled decision_records/investigation_records
           relationships already known (e.g., the fallback-bug
           investigation LED_TO the fix decision)
Phase 2 — Node/edge query layer (mirrors ate_queries.py's pattern exactly)
Phase 3 — Cytoscape.js screen: nav link, container, route, render function
           (same 4-piece pattern as Cost Intelligence Center)
Phase 4 — Command Chat integration for multi-hop questions only
           (single-lookup questions already work via search_decisions()/
           search_investigations(), no graph dependency)
```
