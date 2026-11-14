"""Fill SprintBoard with a demo project so every screen has data.

Run:  python seed.py           (adds demo data once)
      python seed.py --reset   (wipes the database first)

Demo logins (password for all: demo123)
  asha@demo.com   Scrum Master
  ravi@demo.com   Product Owner
  meera@demo.com  Developer
  karan@demo.com  Developer
"""
import os
import sys
from datetime import date, datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("SPRINTBOARD_DB", os.path.join(BASE, "sprintboard.db"))
if "--reset" in sys.argv and os.path.exists(DB_PATH):
    os.remove(DB_PATH)

from werkzeug.security import generate_password_hash  # noqa: E402

import app as sb  # noqa: E402  (creates the tables)

today = date.today()


def day(offset):
    return (today + timedelta(days=offset)).isoformat()


def stamp(offset, hour=15):
    d = today + timedelta(days=offset)
    return datetime(d.year, d.month, d.day, hour, 0).isoformat(timespec="seconds")


def main():
    db = sb.connect()
    if db.execute("SELECT 1 FROM users WHERE email='asha@demo.com'").fetchone():
        print("Demo data already exists. Use  python seed.py --reset  to start fresh.")
        return

    users = {}
    for name, email in [("Asha Verma", "asha@demo.com"), ("Ravi Kumar", "ravi@demo.com"),
                        ("Meera Nair", "meera@demo.com"), ("Karan Singh", "karan@demo.com")]:
        cur = db.execute(
            "INSERT INTO users (name, email, password_hash, created_at) VALUES (?,?,?,?)",
            (name, email, generate_password_hash("demo123"), stamp(-40)))
        users[name.split()[0]] = cur.lastrowid

    pid = db.execute(
        "INSERT INTO projects (name, key, description, owner_id, created_at) VALUES (?,?,?,?,?)",
        ("Campus Event Portal", "CEP",
         "Website for students to browse, register for and manage college events.",
         users["Asha"], stamp(-40))).lastrowid
    for who, role in [("Asha", "scrum_master"), ("Ravi", "product_owner"),
                      ("Meera", "developer"), ("Karan", "developer")]:
        db.execute("INSERT INTO members VALUES (?,?,?)", (pid, users[who], role))

    counter = {"n": 0}

    def task(title, points, sprint=None, status="todo", who=None, done=None,
             ttype="story", priority="medium", due=None, desc=""):
        counter["n"] += 1
        return db.execute(
            """INSERT INTO tasks (project_id, number, sprint_id, title, description, type, priority,
                                  points, status, assignee_id, due_date, position, board_pos,
                                  created_by, created_at, completed_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (pid, counter["n"], sprint, title, desc, ttype, priority, points, status,
             users.get(who), due, counter["n"], counter["n"], users["Ravi"], stamp(-38),
             stamp(done) if done is not None else None)).lastrowid

    def sprint(name, goal, start, end, status, committed=0, completed=0, completed_at=None):
        return db.execute(
            """INSERT INTO sprints (project_id, name, goal, start_date, end_date, status,
                                    committed_points, completed_points, completed_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (pid, name, goal, day(start), day(end), status, committed, completed,
             stamp(completed_at) if completed_at is not None else None)).lastrowid

    # Sprint 1 (completed): 21 committed, 18 done
    s1 = sprint("Sprint 1", "Users can sign up and log in", -34, -21, "completed", 21, 18, -21)
    task("Set up project repository and CI", 2, s1, "done", "Karan", -33, "task")
    task("Design database schema", 3, s1, "done", "Meera", -31, "task", "high")
    task("User registration form", 5, s1, "done", "Meera", -28, priority="high")
    task("Login and logout", 5, s1, "done", "Karan", -25, priority="high")
    task("Password reset by email", 3, s1, "done", "Karan", -22)

    # Sprint 2 (completed): 24 committed, 22 done
    s2 = sprint("Sprint 2", "Students can browse and view events", -20, -7, "completed", 24, 22, -7)
    task("Event listing page", 5, s2, "done", "Meera", -18, priority="high")
    task("Event detail page", 3, s2, "done", "Karan", -16)
    task("Search events by name", 3, s2, "done", "Meera", -14)
    task("Filter events by category and date", 5, s2, "done", "Karan", -11)
    task("Organiser can create an event", 5, s2, "done", "Meera", -9, priority="high")
    task("Fix: long event titles overflow card", 1, s2, "done", "Karan", -8, "bug", "low")

    # Sprint 3 (active): started 6 days ago, 7 days left
    s3 = sprint("Sprint 3", "Students can register for events", -6, 7, "active", 26)
    task("Register for an event", 5, s3, "done", "Meera", -5, priority="high",
         desc="As a student, I want to register for an event so that I get a seat.\n\n"
              "Acceptance criteria:\n- Register button on event page\n"
              "- Seat count decreases\n- Cannot register twice")
    task("Show my registered events", 3, s3, "done", "Karan", -4)
    task("Cancel a registration", 2, s3, "done", "Karan", -2)
    task("Email confirmation on registration", 3, s3, "in_review", "Meera", due=day(1))
    task("Seat limit and waiting list", 5, s3, "in_progress", "Karan", priority="high", due=day(3))
    task("Organiser sees attendee list", 3, s3, "in_progress", "Meera", due=day(4))
    task("Export attendee list as CSV", 2, s3, "todo", "Karan", due=day(6), ttype="task")
    task("Fix: wrong time zone on event page", 1, s3, "todo", None, ttype="bug", priority="high")
    task("QR code ticket for each registration", 2, s3, "todo", None, priority="low")

    # Backlog
    task("Password reset link expires after 30 minutes", 3, None, priority="medium")  # carried over
    task("Event reminder notification one day before", 3, priority="high")
    task("Organiser dashboard with registration counts", 5, priority="high")
    task("Student profile page", 3)
    task("Feedback form after an event", 3)
    task("Admin can approve or reject events", 5, priority="high")
    task("Dark mode", 2, priority="low")
    task("Fix: search is case-sensitive", 1, ttype="bug")
    task("Share event link on WhatsApp", 1, priority="low", ttype="task")

    first_active = db.execute(
        "SELECT id FROM tasks WHERE sprint_id=? AND status='in_progress' LIMIT 1", (s3,)).fetchone()[0]
    db.execute("INSERT INTO comments (task_id, user_id, body, created_at) VALUES (?,?,?,?)",
               (first_active, users["Ravi"],
                "Waiting list should be first come, first served.", stamp(-3, 11)))
    db.execute("INSERT INTO comments (task_id, user_id, body, created_at) VALUES (?,?,?,?)",
               (first_active, users["Karan"],
                "Understood. Seat limit is done, starting on the waiting list today.", stamp(-1, 10)))
    db.commit()
    db.close()
    print("Demo data added. Log in with  asha@demo.com / demo123")


if __name__ == "__main__":
    main()
