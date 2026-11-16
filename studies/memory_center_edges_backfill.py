"""
MEMORY CENTER PHASE 1 — graph_edges backfill.

Every edge below connects two records that are genuinely related in
this project's real history — not a complete-the-grid exercise.
Several decisions and investigations are deliberately left with few
or no edges, because forcing connections that aren't real would
recreate exactly the "clutter" failure mode the Memory Center research
warned about (Obsidian's own documented graph-noise problem).

Looks up decision/investigation IDs by topic string, not hardcoded
row numbers -- safe regardless of insertion order on this specific
database.

Run once, on the Mac Mini, AFTER both backfill scripts:
    python3 memory_center_edges_backfill.py
"""
import command_chat_writer as cc

d = cc.decision_id_by_topic
i = cc.investigation_id_by_topic

# (source_type, source_id_or_topic_lookup, edge_type, target_type, target_id_or_topic_lookup)
EDGES = [
    # Investigations that examined a system
    ("system", "Dataset B", "INVESTIGATED_BY", "investigation", i("Fallback-year leakage bug")),
    ("system", "ATE", "INVESTIGATED_BY", "investigation", i("ATE archive-verification findings")),
    ("system", "Dataset B", "INVESTIGATED_BY", "investigation", i("get_dataset_b_player crash on missing warehouse file")),
    ("system", "Command Chat", "INVESTIGATED_BY", "investigation", i("command_chat_engine build_request() NameError")),
    ("system", "Command Chat", "INVESTIGATED_BY", "investigation", i("pick_from_eval missing eval_id in its 'pick' sub-dict")),
    ("system", "Mission Control", "INVESTIGATED_BY", "investigation", i("pick_from_eval missing eval_id in its 'pick' sub-dict")),
    ("system", "Cost Intelligence", "INVESTIGATED_BY", "investigation", i("avg_cost_per_evaluation averaging bug")),
    ("system", "Cost Intelligence", "INVESTIGATED_BY", "investigation", i("CT timezone day-boundary correctness")),
    ("system", "ATE", "INVESTIGATED_BY", "investigation", i("Moneyline vs props section-format divergence")),
    ("system", "Command Chat", "INVESTIGATED_BY", "investigation", i("Command Chat UX: pre-existing implementation audit")),
    ("system", "Command Chat", "INVESTIGATED_BY", "investigation", i("Model/profile selector wiring audit")),
    ("system", "Dataset B", "INVESTIGATED_BY", "investigation", i("Dataset B name-resolution: where does the real matching logic live")),
    ("system", "Command Chat", "INVESTIGATED_BY", "investigation", i("command_chat.db existed but was uninitialized")),
    ("system", "Command Chat", "INVESTIGATED_BY", "investigation", i("Test-harness DOM stub limitations during Command Chat UX testing")),

    # Investigations that led directly to a decision
    ("investigation", i("ATE archive-verification findings"), "LED_TO", "decision", d("ATE built natively instead of Langfuse")),
    ("investigation", i("ATE archive-verification findings"), "LED_TO", "decision", d("checkpoint_stamps approved, confidence_ledger_events held")),
    ("investigation", i("Compliance Confidence Ledger — tracing score_adjustments to its source"), "LED_TO", "decision", d("Compliance Confidence Ledger — no new table")),
    ("investigation", i("Dataset B name-resolution: where does the real matching logic live"), "LED_TO", "decision", d("Name-resolution fix as a retry layer, not a rewrite")),
    ("investigation", i("GRADE/confidence-math format divergence across evaluations"), "LED_TO", "decision", d("checkpoint_stamps approved, confidence_ledger_events held")),

    # Decisions that depend on a system
    ("decision", d("Top 100 ATP/WTA seed list"), "DEPENDS_ON", "system", "Dataset B"),
    ("decision", d("checkpoint_stamps approved, confidence_ledger_events held"), "DEPENDS_ON", "system", "ATE"),
    ("decision", d("Compliance Confidence Ledger — no new table"), "DEPENDS_ON", "system", "Dataset A"),
    ("decision", d("trace_id linkage via output-parameter, not return-value change"), "DEPENDS_ON", "system", "ATE"),
    ("decision", d("Cost Intelligence Center built on ATE, not Langfuse"), "DEPENDS_ON", "system", "ATE"),
    ("decision", d("Command Chat memory: SQLite + FTS5, not Mem0/Qdrant"), "DEPENDS_ON", "system", "Command Chat"),
    ("decision", d("Command Chat Mission Control placement: hybrid"), "DEPENDS_ON", "system", "Command Chat"),
    ("decision", d("Command Chat Mission Control placement: hybrid"), "DEPENDS_ON", "system", "Mission Control"),
    ("decision", d("Memory Center graph library: Cytoscape.js"), "DEPENDS_ON", "system", "Mission Control"),

    # Decisions that depend on an earlier decision
    ("decision", d("Memory Center Related panel adopted from Capacities"), "DEPENDS_ON", "decision", d("Memory Center: search-first, graph-second")),
    ("decision", d("Memory Center node/edge types finalized at 4 and 4"), "DEPENDS_ON", "decision", d("Memory Center graph library: Cytoscape.js")),

    # System-to-system dependencies (confirmed real, from ATE/Command Chat's own code)
    ("system", "Command Chat", "DEPENDS_ON", "system", "ATE"),
    ("system", "Command Chat", "DEPENDS_ON", "system", "Dataset A"),
    ("system", "Command Chat", "DEPENDS_ON", "system", "Dataset B"),
    ("system", "Command Chat", "DEPENDS_ON", "system", "Cost Intelligence"),
    ("system", "Cost Intelligence", "DEPENDS_ON", "system", "ATE"),
    ("system", "ATE", "DEPENDS_ON", "system", "Dataset A"),
]


def run():
    count = 0
    skipped = 0
    for source_type, source_id, edge_type, target_type, target_id in EDGES:
        if source_id is None or target_id is None:
            skipped += 1
            continue
        cc.add_edge(source_type, source_id, edge_type, target_type, target_id)
        count += 1
    print(f"Backfilled {count} edges.")
    if skipped:
        print(f"Skipped {skipped} edge(s) — a referenced topic wasn't found in this "
              f"database (check that both prior backfill scripts ran successfully).")


if __name__ == "__main__":
    run()
