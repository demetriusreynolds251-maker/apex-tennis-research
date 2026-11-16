"""
MEMORY CENTER READINESS AUDIT — run this on the Mac Mini, not in any
sandbox, for a real answer. Read-only. Touches nothing.

Usage:
    python3 memory_center_audit.py
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "command_chat.db"

# Thresholds from the Memory Center reviews: 15-20 on EACH side
# (decisions AND investigations), not a combined total — a graph with
# 20 decisions and 0 investigations is just as informative-poor as
# the reverse, since INVESTIGATED_BY/LED_TO edges need both sides
# to exist to connect anything.
THRESHOLD_LOW = 15
THRESHOLD_HIGH = 20


def audit(db_path=None):
    path = db_path or DB_PATH
    if not Path(path).exists():
        return {"error": f"command_chat.db not found at {path}"}

    conn = sqlite3.connect(path)

    decisions = conn.execute("SELECT COUNT(*) FROM decision_records").fetchone()[0]
    investigations = conn.execute("SELECT COUNT(*) FROM investigation_records").fetchone()[0]

    # graph_edges doesn't exist until Phase 1 of the Memory Center build
    # is actually implemented -- if it's not there yet, that's the
    # honest answer (0 relationships), not an error.
    try:
        edges = conn.execute("SELECT COUNT(*) FROM graph_edges").fetchone()[0]
        edges_table_exists = True
    except sqlite3.OperationalError:
        edges = 0
        edges_table_exists = False

    conn.close()

    graph_worthy_total = decisions + investigations

    decisions_remaining = max(0, THRESHOLD_LOW - decisions)
    investigations_remaining = max(0, THRESHOLD_LOW - investigations)
    decisions_met = decisions >= THRESHOLD_LOW
    investigations_met = investigations >= THRESHOLD_LOW

    verdict = "GO" if (decisions_met and investigations_met) else "NOT YET"

    return {
        "decision_records_count": decisions,
        "investigation_records_count": investigations,
        "graph_worthy_records_total": graph_worthy_total,
        "graph_relationships_total": edges,
        "graph_edges_table_exists": edges_table_exists,
        "threshold_low": THRESHOLD_LOW,
        "threshold_high": THRESHOLD_HIGH,
        "decisions_met_threshold": decisions_met,
        "investigations_met_threshold": investigations_met,
        "decisions_remaining_to_threshold": decisions_remaining,
        "investigations_remaining_to_threshold": investigations_remaining,
        "verdict": verdict,
    }


def print_report(r):
    if "error" in r:
        print(r["error"])
        return
    print("=" * 60)
    print("MEMORY CENTER READINESS AUDIT")
    print("=" * 60)
    print(f"decision_records:       {r['decision_records_count']}")
    print(f"investigation_records:  {r['investigation_records_count']}")
    print(f"graph-worthy total:     {r['graph_worthy_records_total']}")
    print(f"graph relationships:    {r['graph_relationships_total']}"
          + ("" if r["graph_edges_table_exists"] else "  (graph_edges table doesn't exist yet — Phase 1 not built)"))
    print("-" * 60)
    print(f"threshold (each side):  {r['threshold_low']}-{r['threshold_high']}")
    if r["verdict"] == "GO":
        print()
        print("VERDICT: GO — both decision_records and investigation_records")
        print("have met the threshold. Memory Center Phase 1 can begin.")
    else:
        print()
        print("VERDICT: NOT YET")
        if not r["decisions_met_threshold"]:
            print(f"  decision_records needs {r['decisions_remaining_to_threshold']} more "
                  f"(has {r['decision_records_count']}, needs {r['threshold_low']})")
        if not r["investigations_met_threshold"]:
            print(f"  investigation_records needs {r['investigations_remaining_to_threshold']} more "
                  f"(has {r['investigation_records_count']}, needs {r['threshold_low']})")
    print("=" * 60)


if __name__ == "__main__":
    print_report(audit())
