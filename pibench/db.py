"""Observable-state SQL interface.

Builds an in-memory SQLite snapshot of everything the agent is allowed to see and
runs a read-only query against it. Hidden fields (h_*, latent quality, hotness,
crowding, agency preferences, morale) are never exported.
"""
from __future__ import annotations

import json
import sqlite3

from .world import ApiError, World

MAX_ROWS = 200


def build_db(w: World) -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    cur = con.cursor()

    cur.execute("""CREATE TABLE students (
        id TEXT, name TEXT, role TEXT, status TEXT, arrived_month INT,
        left_month INT, stipend REAL, mentoring_hours REAL,
        papers_accepted INT, first_author_accepted INT, contract_end INT)""")
    for s in w.students.values():
        cur.execute("INSERT INTO students VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (s.id, s.name, s.role, s.status, s.arrived_month, s.left_month,
                     s.stipend, s.mentoring, s.papers_accepted,
                     s.first_author_accepted, s.contract_end))

    cur.execute("""CREATE TABLE student_reports (
        student_id TEXT, month INT, report_quality REAL, meeting_sentiment REAL)""")
    for s in w.students.values():
        for m, rq, sent in s.reports:
            cur.execute("INSERT INTO student_reports VALUES (?,?,?,?)", (s.id, m, rq, sent))

    cur.execute("""CREATE TABLE applicants (
        id TEXT, season_year INT, pool TEXT, name TEXT, transcript REAL, letter REAL,
        interview REAL, status TEXT)""")
    for a in w.applicants.values():
        cur.execute("INSERT INTO applicants VALUES (?,?,?,?,?,?,?,?)",
                    (a.id, a.season_year, a.pool, a.name, a.transcript, a.letter,
                     a.interview, a.status))

    cur.execute("""CREATE TABLE projects (
        id TEXT, topic TEXT, tier INT, status TEXT, started_month INT,
        ended_month INT, progress_pct REAL, monthly_compute REAL,
        members TEXT, draft_id TEXT, scooped_times INT)""")
    for p in w.projects.values():
        cur.execute("INSERT INTO projects VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (p.id, p.topic, p.tier, p.status, p.started_month, p.ended_month,
                     round(100 * p.progress / p.work_required, 1), p.compute,
                     json.dumps(p.members), p.draft_id, p.scooped_times))

    cur.execute("""CREATE TABLE drafts (
        id TEXT, project_id TEXT, topic TEXT, tier INT, status TEXT,
        created_month INT, authors TEXT, polish_hours REAL, revisions INT,
        salvage INT, collab INT)""")
    for d in w.drafts.values():
        cur.execute("INSERT INTO drafts VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (d.id, d.project_id, d.topic, d.tier, d.status, d.created_month,
                     json.dumps(d.authors), d.polish_hours, d.revisions,
                     int(d.salvage), int(d.collab)))

    cur.execute("""CREATE TABLE submissions (
        id TEXT, draft_id TEXT, venue TEXT, status TEXT, submitted_month INT,
        decision_month INT, reviewer_scores TEXT)""")
    for s in w.submissions.values():
        scores = json.dumps(s.reviewer_scores) if s.reviewer_scores is not None else None
        cur.execute("INSERT INTO submissions VALUES (?,?,?,?,?,?,?)",
                    (s.id, s.draft_id, s.venue, s.status, s.submitted_month,
                     s.decision_month, scores))

    cur.execute("""CREATE TABLE publications (
        id TEXT, draft_id TEXT, venue TEXT, topic TEXT, tier INT,
        published_month INT, citations INT, authors TEXT, collab INT)""")
    cur.execute("""CREATE TABLE citations_monthly (
        publication_id TEXT, month INT, citations INT)""")
    for p in w.publications.values():
        if p.published_month > w.month:
            continue
        cur.execute("INSERT INTO publications VALUES (?,?,?,?,?,?,?,?,?)",
                    (p.id, p.draft_id, p.venue, p.topic, p.tier, p.published_month,
                     p.citations, json.dumps(p.authors), int(p.collab)))
        for m, c in p.cite_history:
            cur.execute("INSERT INTO citations_monthly VALUES (?,?,?)", (p.id, m, c))

    cur.execute("""CREATE TABLE grant_calls (
        id TEXT, agency TEXT, award REAL, duration_months INT,
        open_month INT, close_month INT)""")
    for c in w.calls.values():
        if c.open_month <= w.month:
            cur.execute("INSERT INTO grant_calls VALUES (?,?,?,?,?,?)",
                        (c.id, c.agency, c.award, c.duration, c.open_month, c.close_month))

    cur.execute("""CREATE TABLE proposals (
        id TEXT, call_id TEXT, agency TEXT, topic TEXT, status TEXT,
        hours REAL, submitted_month INT, decision_month INT, attached TEXT)""")
    for p in w.proposals.values():
        cur.execute("INSERT INTO proposals VALUES (?,?,?,?,?,?,?,?,?)",
                    (p.id, p.call_id, p.agency, p.topic, p.status, p.hours,
                     p.submitted_month, p.decision_month, json.dumps(p.attached)))

    cur.execute("""CREATE TABLE awards (
        id TEXT, agency TEXT, total REAL, monthly REAL, start_month INT, end_month INT)""")
    for a in w.awards.values():
        cur.execute("INSERT INTO awards VALUES (?,?,?,?,?,?)",
                    (a.id, a.agency, a.total, a.monthly, a.start_month, a.end_month))

    cur.execute("CREATE TABLE ledger (month INT, category TEXT, amount REAL, note TEXT)")
    cur.executemany("INSERT INTO ledger VALUES (?,?,?,?)", w.ledger)

    cur.execute("CREATE TABLE news (month INT, kind TEXT, topic TEXT, text TEXT)")
    cur.executemany("INSERT INTO news VALUES (?,?,?,?)",
                    [(x.month, x.kind, x.topic, x.text) for x in w.news])

    cur.execute("CREATE TABLE preprint_feed (month INT, topic TEXT, preprint_count INT)")
    cur.executemany("INSERT INTO preprint_feed VALUES (?,?,?)", w.preprints)

    cur.execute("""CREATE TABLE conference_reports (
        month INT, venue TEXT, topic TEXT, accepted_papers INT)""")
    cur.executemany("INSERT INTO conference_reports VALUES (?,?,?,?)", w.conf_reports)

    cur.execute("""CREATE TABLE events (
        id TEXT, kind TEXT, month INT, respond_by INT, status TEXT, details TEXT)""")
    for e in w.events.values():
        details = {k: v for k, v in e.payload.items() if not k.startswith("deliver")}
        cur.execute("INSERT INTO events VALUES (?,?,?,?,?,?)",
                    (e.id, e.kind, e.month, e.expires, e.status, json.dumps(details)))

    cur.execute("""CREATE TABLE lab_monthly (
        month INT, budget REAL, reputation_standing TEXT, students INT,
        active_projects INT, publications INT, citations_total INT,
        attention_used REAL)""")
    for row in w.monthly_stats:
        standing = ("unknown" if row["reputation"] < 2.5 else
                    "rising" if row["reputation"] < 4 else
                    "established" if row["reputation"] < 6 else "renowned")
        cur.execute("INSERT INTO lab_monthly VALUES (?,?,?,?,?,?,?,?)",
                    (row["month"], row["budget"], standing, row["students"],
                     row["projects"], row["publications"], row["citations"],
                     row["attention_used"]))

    cur.execute("CREATE TABLE venues (name TEXT, kind TEXT, deadlines TEXT, "
                "decision_delay INT)")
    from .config import VENUES
    for name, v in VENUES.items():
        cur.execute("INSERT INTO venues VALUES (?,?,?,?)",
                    (name, v["kind"], json.dumps(v["deadlines"]), v["delay"]))

    cur.execute("CREATE TABLE topics (name TEXT)")
    from .config import TOPICS
    cur.executemany("INSERT INTO topics VALUES (?)", [(t,) for t in TOPICS])

    con.commit()
    return con


def run_query(w: World, sql: str):
    if not isinstance(sql, str):
        raise ApiError("query(sql) takes a SQL string")
    lowered = sql.strip().lower()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise ApiError("only SELECT queries are allowed")
    con = build_db(w)
    try:
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchmany(MAX_ROWS)
        return [dict(zip(cols, r)) for r in rows]
    except sqlite3.Error as e:
        raise ApiError(f"SQL error: {e}")
    finally:
        con.close()
