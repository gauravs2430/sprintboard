"""SprintBoard - a lightweight Agile/Scrum project management tool.

Run:  python app.py   then open http://127.0.0.1:5000
"""
import os
import secrets
import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("SPRINTBOARD_DB", os.path.join(BASE, "sprintboard.db"))

STATUSES = [("todo", "To Do"), ("in_progress", "In Progress"),
            ("in_review", "In Review"), ("done", "Done")]
ROLES = [("scrum_master", "Scrum Master"), ("product_owner", "Product Owner"),
         ("developer", "Developer")]
TYPES = ["story", "task", "bug"]
PRIORITIES = ["high", "medium", "low"]
STATUS_KEYS = [s[0] for s in STATUSES]
ROLE_KEYS = [r[0] for r in ROLES]

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    key TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    owner_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS members (
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    role TEXT NOT NULL,
    PRIMARY KEY (project_id, user_id)
);
CREATE TABLE IF NOT EXISTS sprints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    goal TEXT NOT NULL DEFAULT '',
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planned',
    committed_points INTEGER NOT NULL DEFAULT 0,
    completed_points INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    number INTEGER NOT NULL,
    sprint_id INTEGER REFERENCES sprints(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL DEFAULT 'story',
    priority TEXT NOT NULL DEFAULT 'medium',
    points INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'todo',
    assignee_id INTEGER REFERENCES users(id),
    due_date TEXT,
    position INTEGER NOT NULL DEFAULT 0,
    board_pos INTEGER NOT NULL DEFAULT 0,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    body TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _secret_key():
    path = os.path.join(BASE, ".secret_key")
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip()
    key = secrets.token_hex(32)
    with open(path, "w") as f:
        f.write(key)
    return key


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SPRINTBOARD_SECRET") or _secret_key()


# ---------------------------------------------------------------- database
def connect():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def get_db():
    if "db" not in g:
        g.db = connect()
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = connect()
    db.executescript(SCHEMA)
    db.commit()
    db.close()


def now():
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------- helpers
def parse_date(value):
    try:
        return date.fromisoformat((value or "").strip()).isoformat()
    except ValueError:
        return None


def clean_points(value):
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return 0


def make_key(name):
    words = [w for w in "".join(c if c.isalnum() else " " for c in name).split()]
    key = "".join(w[0] for w in words)[:4] if len(words) > 1 else name[:3]
    key = "".join(c for c in key if c.isalnum()).upper()
    return key or "PRJ"


@app.template_filter("nice_date")
def nice_date(value):
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).strftime("%d %b")
    except ValueError:
        return value


@app.template_filter("nice_datetime")
def nice_datetime(value):
    try:
        return datetime.fromisoformat(value).strftime("%d %b %Y, %H:%M")
    except (ValueError, TypeError):
        return value or ""


@app.template_filter("initials")
def initials(name):
    parts = (name or "?").split()
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()


@app.context_processor
def inject_globals():
    return dict(STATUSES=STATUSES, ROLES=ROLES, TYPES=TYPES, PRIORITIES=PRIORITIES,
                role_label=dict(ROLES), status_label=dict(STATUSES),
                csrf_token=csrf_token, today=date.today().isoformat())


# ---------------------------------------------------------------- security
def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


@app.before_request
def before_request():
    g.user = None
    uid = session.get("user_id")
    if uid:
        g.user = get_db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if request.method == "POST":
        sent = request.form.get("_csrf") or request.headers.get("X-CSRF-Token")
        if not sent or not secrets.compare_digest(sent, session.get("_csrf", "")):
            abort(400, "Invalid or missing form token. Reload the page and try again.")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            if request.path.startswith("/api/"):
                abort(401)
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def project_ctx(pid):
    """Return (project, role) for the logged-in user or abort."""
    db = get_db()
    project = db.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    if not project:
        abort(404)
    m = db.execute("SELECT role FROM members WHERE project_id=? AND user_id=?",
                   (pid, g.user["id"])).fetchone()
    if not m:
        abort(403)
    return project, m["role"]


def require_role(role, *allowed):
    if role not in allowed:
        abort(403)


TASK_SELECT = """
SELECT t.*, u.name AS assignee_name
FROM tasks t LEFT JOIN users u ON u.id = t.assignee_id
"""


def project_members(pid):
    return get_db().execute(
        """SELECT u.id, u.name, u.email, m.role FROM members m
           JOIN users u ON u.id = m.user_id WHERE m.project_id=?
           ORDER BY u.name""", (pid,)).fetchall()


def average_velocity(pid):
    rows = get_db().execute(
        """SELECT completed_points FROM sprints WHERE project_id=? AND status='completed'
           ORDER BY completed_at DESC LIMIT 3""", (pid,)).fetchall()
    if not rows:
        return None
    return round(sum(r["completed_points"] for r in rows) / len(rows))


def set_status(db, task, new_status):
    """Change a task's status, keeping completed_at in sync."""
    if new_status not in STATUS_KEYS or new_status == task["status"]:
        return
    completed_at = task["completed_at"]
    if new_status == "done":
        completed_at = now()
    elif task["status"] == "done":
        completed_at = None
    db.execute("UPDATE tasks SET status=?, completed_at=? WHERE id=?",
               (new_status, completed_at, task["id"]))


# ---------------------------------------------------------------- auth
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        db = get_db()
        if not name or "@" not in email:
            flash("Enter your name and a valid email.", "error")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
        elif db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            flash("An account with that email already exists.", "error")
        else:
            cur = db.execute(
                "INSERT INTO users (name, email, password_hash, created_at) VALUES (?,?,?,?)",
                (name, email, generate_password_hash(password), now()))
            db.commit()
            session.clear()
            session["user_id"] = cur.lastrowid
            return redirect(url_for("dashboard"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = get_db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
            session.clear()
            session["user_id"] = user["id"]
            nxt = request.args.get("next", "")
            if not nxt.startswith("/") or nxt.startswith("//"):
                nxt = url_for("dashboard")
            return redirect(nxt)
        flash("Wrong email or password.", "error")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------- dashboard
@app.route("/")
@login_required
def dashboard():
    db = get_db()
    projects = db.execute(
        """SELECT p.*, m.role,
             (SELECT COUNT(*) FROM tasks t WHERE t.project_id=p.id AND t.status!='done') AS open_count,
             (SELECT COUNT(*) FROM members mm WHERE mm.project_id=p.id) AS member_count,
             (SELECT name FROM sprints s WHERE s.project_id=p.id AND s.status='active') AS active_sprint
           FROM projects p JOIN members m ON m.project_id=p.id
           WHERE m.user_id=? ORDER BY p.created_at DESC""", (g.user["id"],)).fetchall()
    my_tasks = db.execute(
        """SELECT t.*, p.name AS project_name, p.key AS project_key, s.name AS sprint_name
           FROM tasks t JOIN projects p ON p.id=t.project_id
           JOIN members m ON m.project_id=p.id AND m.user_id=?
           LEFT JOIN sprints s ON s.id=t.sprint_id
           WHERE t.assignee_id=? AND t.status!='done'
           ORDER BY (t.due_date IS NULL), t.due_date, t.id""",
        (g.user["id"], g.user["id"])).fetchall()
    return render_template("dashboard.html", projects=projects, my_tasks=my_tasks)


@app.route("/projects", methods=["POST"])
@login_required
def create_project():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Project name is required.", "error")
        return redirect(url_for("dashboard"))
    db = get_db()
    cur = db.execute(
        "INSERT INTO projects (name, key, description, owner_id, created_at) VALUES (?,?,?,?,?)",
        (name, make_key(name), request.form.get("description", "").strip(), g.user["id"], now()))
    db.execute("INSERT INTO members (project_id, user_id, role) VALUES (?,?,?)",
               (cur.lastrowid, g.user["id"], "scrum_master"))
    db.commit()
    flash("Project created. You are its Scrum Master.", "ok")
    return redirect(url_for("backlog", pid=cur.lastrowid))


@app.route("/p/<int:pid>/delete", methods=["POST"])
@login_required
def delete_project(pid):
    project, role = project_ctx(pid)
    if project["owner_id"] != g.user["id"]:
        abort(403)
    db = get_db()
    db.execute("DELETE FROM projects WHERE id=?", (pid,))
    db.commit()
    flash("Project deleted.", "ok")
    return redirect(url_for("dashboard"))


# ---------------------------------------------------------------- backlog & sprint planning
@app.route("/p/<int:pid>")
@login_required
def project_home(pid):
    project_ctx(pid)
    return redirect(url_for("backlog", pid=pid))


@app.route("/p/<int:pid>/backlog")
@login_required
def backlog(pid):
    project, role = project_ctx(pid)
    db = get_db()
    backlog_tasks = db.execute(
        TASK_SELECT + "WHERE t.project_id=? AND t.sprint_id IS NULL ORDER BY t.position, t.id",
        (pid,)).fetchall()
    open_sprints = []
    for s in db.execute(
            """SELECT * FROM sprints WHERE project_id=? AND status!='completed'
               ORDER BY (status='active') DESC, start_date, id""", (pid,)).fetchall():
        tasks = db.execute(
            TASK_SELECT + "WHERE t.sprint_id=? ORDER BY t.position, t.id", (s["id"],)).fetchall()
        open_sprints.append({"sprint": s, "tasks": tasks})
    done_sprints = db.execute(
        "SELECT * FROM sprints WHERE project_id=? AND status='completed' ORDER BY completed_at DESC",
        (pid,)).fetchall()
    default_start = date.today()
    return render_template(
        "backlog.html", project=project, role=role, tab="backlog",
        backlog_tasks=backlog_tasks, open_sprints=open_sprints, done_sprints=done_sprints,
        velocity=average_velocity(pid), members=project_members(pid),
        default_start=default_start.isoformat(),
        default_end=(default_start + timedelta(days=13)).isoformat(),
        next_sprint_no=len(open_sprints) + len(done_sprints) + 1)


@app.route("/p/<int:pid>/tasks", methods=["POST"])
@login_required
def create_task(pid):
    project, role = project_ctx(pid)
    title = request.form.get("title", "").strip()
    if not title:
        flash("Give the item a title.", "error")
        return redirect(url_for("backlog", pid=pid))
    db = get_db()
    ttype = request.form.get("type", "story")
    priority = request.form.get("priority", "medium")
    number = db.execute("SELECT COALESCE(MAX(number),0)+1 FROM tasks WHERE project_id=?",
                        (pid,)).fetchone()[0]
    position = db.execute(
        "SELECT COALESCE(MAX(position),0)+1 FROM tasks WHERE project_id=? AND sprint_id IS NULL",
        (pid,)).fetchone()[0]
    db.execute(
        """INSERT INTO tasks (project_id, number, title, description, type, priority, points,
                              position, created_by, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (pid, number, title, request.form.get("description", "").strip(),
         ttype if ttype in TYPES else "story",
         priority if priority in PRIORITIES else "medium",
         clean_points(request.form.get("points")), position, g.user["id"], now()))
    db.commit()
    return redirect(url_for("backlog", pid=pid))


@app.route("/api/p/<int:pid>/reorder", methods=["POST"])
@login_required
def api_reorder(pid):
    """Save the order of the backlog and/or sprint lists after a drag."""
    project_ctx(pid)
    db = get_db()
    data = request.get_json(silent=True) or {}
    for lst in data.get("lists", []):
        sprint_id = lst.get("sprint_id")
        if sprint_id is not None:
            s = db.execute("SELECT status FROM sprints WHERE id=? AND project_id=?",
                           (sprint_id, pid)).fetchone()
            if not s or s["status"] == "completed":
                abort(400)
        for pos, tid in enumerate(lst.get("task_ids", [])):
            db.execute("UPDATE tasks SET sprint_id=?, position=? WHERE id=? AND project_id=?",
                       (sprint_id, pos, tid, pid))
    db.commit()
    return jsonify(ok=True)


@app.route("/p/<int:pid>/sprints", methods=["POST"])
@login_required
def create_sprint(pid):
    project, role = project_ctx(pid)
    require_role(role, "scrum_master")
    name = request.form.get("name", "").strip()
    start = parse_date(request.form.get("start_date"))
    end = parse_date(request.form.get("end_date"))
    if not name or not start or not end:
        flash("A sprint needs a name, a start date and an end date.", "error")
    elif end < start:
        flash("The end date cannot be before the start date.", "error")
    else:
        db = get_db()
        db.execute(
            "INSERT INTO sprints (project_id, name, goal, start_date, end_date) VALUES (?,?,?,?,?)",
            (pid, name, request.form.get("goal", "").strip(), start, end))
        db.commit()
        flash("Sprint created. Drag items into it, then start it.", "ok")
    return redirect(url_for("backlog", pid=pid))


def get_sprint(pid, sid):
    s = get_db().execute("SELECT * FROM sprints WHERE id=? AND project_id=?", (sid, pid)).fetchone()
    if not s:
        abort(404)
    return s


@app.route("/p/<int:pid>/sprints/<int:sid>/start", methods=["POST"])
@login_required
def start_sprint(pid, sid):
    project, role = project_ctx(pid)
    require_role(role, "scrum_master")
    sprint = get_sprint(pid, sid)
    db = get_db()
    if sprint["status"] != "planned":
        abort(400)
    if db.execute("SELECT 1 FROM sprints WHERE project_id=? AND status='active'", (pid,)).fetchone():
        flash("Complete the active sprint before starting another.", "error")
        return redirect(url_for("backlog", pid=pid))
    stats = db.execute("SELECT COUNT(*) c, COALESCE(SUM(points),0) p FROM tasks WHERE sprint_id=?",
                       (sid,)).fetchone()
    if stats["c"] == 0:
        flash("Add at least one item to the sprint before starting it.", "error")
        return redirect(url_for("backlog", pid=pid))
    start = date.fromisoformat(sprint["start_date"])
    end = date.fromisoformat(sprint["end_date"])
    today_ = date.today()
    if not (start <= today_ <= end):  # keep the planned length, begin today
        end = today_ + (end - start)
        start = today_
    db.execute(
        "UPDATE sprints SET status='active', start_date=?, end_date=?, committed_points=? WHERE id=?",
        (start.isoformat(), end.isoformat(), stats["p"], sid))
    db.commit()
    flash(f"{sprint['name']} started.", "ok")
    return redirect(url_for("board", pid=pid))


@app.route("/p/<int:pid>/sprints/<int:sid>/complete", methods=["POST"])
@login_required
def complete_sprint(pid, sid):
    project, role = project_ctx(pid)
    require_role(role, "scrum_master")
    sprint = get_sprint(pid, sid)
    if sprint["status"] != "active":
        abort(400)
    db = get_db()
    total = db.execute("SELECT COALESCE(SUM(points),0) FROM tasks WHERE sprint_id=?",
                       (sid,)).fetchone()[0]
    done = db.execute(
        "SELECT COALESCE(SUM(points),0) FROM tasks WHERE sprint_id=? AND status='done'",
        (sid,)).fetchone()[0]
    unfinished = db.execute(
        "SELECT id FROM tasks WHERE sprint_id=? AND status!='done' ORDER BY position", (sid,)).fetchall()
    top = db.execute(
        "SELECT COALESCE(MIN(position),0) FROM tasks WHERE project_id=? AND sprint_id IS NULL",
        (pid,)).fetchone()[0]
    for i, t in enumerate(unfinished):  # unfinished work returns to the top of the backlog
        db.execute("UPDATE tasks SET sprint_id=NULL, position=? WHERE id=?",
                   (top - len(unfinished) + i, t["id"]))
    db.execute(
        """UPDATE sprints SET status='completed', committed_points=?, completed_points=?,
                              completed_at=? WHERE id=?""", (total, done, now(), sid))
    db.commit()
    msg = f"{sprint['name']} completed: {done} of {total} points done."
    if unfinished:
        msg += f" {len(unfinished)} unfinished item(s) moved back to the backlog."
    flash(msg, "ok")
    return redirect(url_for("reports", pid=pid, sprint=sid))


@app.route("/p/<int:pid>/sprints/<int:sid>/delete", methods=["POST"])
@login_required
def delete_sprint(pid, sid):
    project, role = project_ctx(pid)
    require_role(role, "scrum_master")
    sprint = get_sprint(pid, sid)
    if sprint["status"] != "planned":
        flash("Only a sprint that has not started can be deleted.", "error")
        return redirect(url_for("backlog", pid=pid))
    db = get_db()
    db.execute("UPDATE tasks SET sprint_id=NULL WHERE sprint_id=?", (sid,))
    db.execute("DELETE FROM sprints WHERE id=?", (sid,))
    db.commit()
    flash("Sprint deleted. Its items are back in the backlog.", "ok")
    return redirect(url_for("backlog", pid=pid))


# ---------------------------------------------------------------- board
@app.route("/p/<int:pid>/board")
@login_required
def board(pid):
    project, role = project_ctx(pid)
    db = get_db()
    sprint = db.execute("SELECT * FROM sprints WHERE project_id=? AND status='active'",
                        (pid,)).fetchone()
    columns, days_left = [], None
    if sprint:
        tasks = db.execute(
            TASK_SELECT + "WHERE t.sprint_id=? ORDER BY t.board_pos, t.position, t.id",
            (sprint["id"],)).fetchall()
        for key, label in STATUSES:
            col = [t for t in tasks if t["status"] == key]
            columns.append({"key": key, "label": label, "tasks": col,
                            "points": sum(t["points"] for t in col)})
        days_left = (date.fromisoformat(sprint["end_date"]) - date.today()).days
    return render_template("board.html", project=project, role=role, tab="board",
                           sprint=sprint, columns=columns, days_left=days_left)


@app.route("/api/p/<int:pid>/board", methods=["POST"])
@login_required
def api_board(pid):
    """Move a card to a column and save that column's order."""
    project_ctx(pid)
    db = get_db()
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in STATUS_KEYS:
        abort(400)
    task = db.execute("SELECT * FROM tasks WHERE id=? AND project_id=?",
                      (data.get("task_id"), pid)).fetchone()
    if not task:
        abort(404)
    set_status(db, task, status)
    for pos, tid in enumerate(data.get("order", [])):
        db.execute("UPDATE tasks SET board_pos=? WHERE id=? AND project_id=?", (pos, tid, pid))
    db.commit()
    return jsonify(ok=True)


# ---------------------------------------------------------------- task detail
def get_task(pid, tid):
    t = get_db().execute(TASK_SELECT + "WHERE t.id=? AND t.project_id=?", (tid, pid)).fetchone()
    if not t:
        abort(404)
    return t


@app.route("/p/<int:pid>/task/<int:tid>", methods=["GET", "POST"])
@login_required
def task_detail(pid, tid):
    project, role = project_ctx(pid)
    task = get_task(pid, tid)
    db = get_db()
    sprint = None
    if task["sprint_id"]:
        sprint = db.execute("SELECT * FROM sprints WHERE id=?", (task["sprint_id"],)).fetchone()
    locked = bool(sprint and sprint["status"] == "completed")
    open_sprints = db.execute(
        "SELECT * FROM sprints WHERE project_id=? AND status!='completed' ORDER BY start_date",
        (pid,)).fetchall()
    members = project_members(pid)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        if not title:
            flash("Title cannot be empty.", "error")
            return redirect(url_for("task_detail", pid=pid, tid=tid))
        ttype = request.form.get("type")
        priority = request.form.get("priority")
        assignee = request.form.get("assignee_id") or None
        if assignee is not None:
            assignee = int(assignee) if assignee.isdigit() else None
            if assignee not in [m["id"] for m in members]:
                assignee = None
        sprint_id = task["sprint_id"]
        if not locked:
            raw = request.form.get("sprint_id", "")
            sprint_id = int(raw) if raw.isdigit() else None
            if sprint_id not in [s["id"] for s in open_sprints]:
                sprint_id = None
        db.execute(
            """UPDATE tasks SET title=?, description=?, type=?, priority=?, points=?,
                                assignee_id=?, due_date=?, sprint_id=? WHERE id=?""",
            (title, request.form.get("description", "").strip(),
             ttype if ttype in TYPES else task["type"],
             priority if priority in PRIORITIES else task["priority"],
             clean_points(request.form.get("points")), assignee,
             parse_date(request.form.get("due_date")), sprint_id, tid))
        if not locked:
            set_status(db, task, request.form.get("status"))
        db.commit()
        flash("Saved.", "ok")
        return redirect(url_for("task_detail", pid=pid, tid=tid))

    comments = db.execute(
        """SELECT c.*, u.name AS author FROM comments c JOIN users u ON u.id=c.user_id
           WHERE c.task_id=? ORDER BY c.created_at""", (tid,)).fetchall()
    return render_template("task.html", project=project, role=role, tab="", task=task,
                           sprint=sprint, locked=locked, open_sprints=open_sprints,
                           members=members, comments=comments)


@app.route("/p/<int:pid>/task/<int:tid>/comment", methods=["POST"])
@login_required
def add_comment(pid, tid):
    project_ctx(pid)
    get_task(pid, tid)
    body = request.form.get("body", "").strip()
    if body:
        db = get_db()
        db.execute("INSERT INTO comments (task_id, user_id, body, created_at) VALUES (?,?,?,?)",
                   (tid, g.user["id"], body, now()))
        db.commit()
    return redirect(url_for("task_detail", pid=pid, tid=tid) + "#comments")


@app.route("/p/<int:pid>/task/<int:tid>/delete", methods=["POST"])
@login_required
def delete_task(pid, tid):
    project, role = project_ctx(pid)
    require_role(role, "scrum_master", "product_owner")
    get_task(pid, tid)
    db = get_db()
    db.execute("DELETE FROM tasks WHERE id=?", (tid,))
    db.commit()
    flash("Item deleted.", "ok")
    return redirect(url_for("backlog", pid=pid))


# ---------------------------------------------------------------- team
@app.route("/p/<int:pid>/team")
@login_required
def team(pid):
    project, role = project_ctx(pid)
    return render_template("team.html", project=project, role=role, tab="team",
                           members=project_members(pid))


@app.route("/p/<int:pid>/team/add", methods=["POST"])
@login_required
def add_member(pid):
    project, role = project_ctx(pid)
    require_role(role, "scrum_master")
    db = get_db()
    email = request.form.get("email", "").strip().lower()
    new_role = request.form.get("role", "developer")
    user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not user:
        flash("No account uses that email. Ask them to sign up first.", "error")
    elif db.execute("SELECT 1 FROM members WHERE project_id=? AND user_id=?",
                    (pid, user["id"])).fetchone():
        flash(f"{user['name']} is already on the team.", "error")
    else:
        db.execute("INSERT INTO members (project_id, user_id, role) VALUES (?,?,?)",
                   (pid, user["id"], new_role if new_role in ROLE_KEYS else "developer"))
        db.commit()
        flash(f"{user['name']} added to the team.", "ok")
    return redirect(url_for("team", pid=pid))


def _scrum_master_count(db, pid):
    return db.execute(
        "SELECT COUNT(*) FROM members WHERE project_id=? AND role='scrum_master'", (pid,)).fetchone()[0]


@app.route("/p/<int:pid>/team/<int:uid>/role", methods=["POST"])
@login_required
def change_role(pid, uid):
    project, role = project_ctx(pid)
    require_role(role, "scrum_master")
    db = get_db()
    new_role = request.form.get("role")
    m = db.execute("SELECT role FROM members WHERE project_id=? AND user_id=?", (pid, uid)).fetchone()
    if not m or new_role not in ROLE_KEYS:
        abort(400)
    if m["role"] == "scrum_master" and new_role != "scrum_master" and _scrum_master_count(db, pid) == 1:
        flash("A project needs at least one Scrum Master.", "error")
    else:
        db.execute("UPDATE members SET role=? WHERE project_id=? AND user_id=?", (new_role, pid, uid))
        db.commit()
        flash("Role updated.", "ok")
    return redirect(url_for("team", pid=pid))


@app.route("/p/<int:pid>/team/<int:uid>/remove", methods=["POST"])
@login_required
def remove_member(pid, uid):
    project, role = project_ctx(pid)
    require_role(role, "scrum_master")
    db = get_db()
    m = db.execute("SELECT role FROM members WHERE project_id=? AND user_id=?", (pid, uid)).fetchone()
    if not m:
        abort(404)
    if uid == project["owner_id"]:
        flash("The project owner cannot be removed.", "error")
    elif m["role"] == "scrum_master" and _scrum_master_count(db, pid) == 1:
        flash("A project needs at least one Scrum Master.", "error")
    else:
        db.execute("UPDATE tasks SET assignee_id=NULL WHERE project_id=? AND assignee_id=?", (pid, uid))
        db.execute("DELETE FROM members WHERE project_id=? AND user_id=?", (pid, uid))
        db.commit()
        flash("Member removed. Their tasks are now unassigned.", "ok")
    return redirect(url_for("team", pid=pid))


# ---------------------------------------------------------------- reports
def burndown_data(sprint):
    """Remaining story points per day of the sprint, plus the ideal line."""
    db = get_db()
    start = date.fromisoformat(sprint["start_date"])
    end = date.fromisoformat(sprint["end_date"])
    tasks = db.execute("SELECT points, status, completed_at FROM tasks WHERE sprint_id=?",
                       (sprint["id"],)).fetchall()
    if sprint["status"] == "completed":
        total = sprint["committed_points"]
        last = min(end, date.fromisoformat(sprint["completed_at"][:10]))
    else:
        total = sum(t["points"] for t in tasks)
        last = min(end, date.today())
    n = (end - start).days + 1
    labels, ideal, actual = [], [], []
    for i in range(n):
        day = start + timedelta(days=i)
        labels.append(day.strftime("%d %b"))
        ideal.append(round(total * (1 - i / (n - 1)), 1) if n > 1 else 0)
        if day <= last and sprint["status"] != "planned":
            burned = sum(t["points"] for t in tasks
                         if t["status"] == "done" and t["completed_at"]
                         and t["completed_at"][:10] <= day.isoformat())
            actual.append(total - burned)
        else:
            actual.append(None)
    done = sum(t["points"] for t in tasks if t["status"] == "done")
    return {"labels": labels, "ideal": ideal, "actual": actual,
            "total": total, "done": done, "remaining": max(total - done, 0)}


@app.route("/p/<int:pid>/reports")
@login_required
def reports(pid):
    project, role = project_ctx(pid)
    db = get_db()
    sprints = db.execute(
        """SELECT * FROM sprints WHERE project_id=? AND status!='planned'
           ORDER BY (status='active') DESC, completed_at DESC""", (pid,)).fetchall()
    selected = None
    wanted = request.args.get("sprint", type=int)
    for s in sprints:
        if s["id"] == wanted:
            selected = s
    if selected is None and sprints:
        selected = sprints[0]

    burndown, workload, days_left = None, None, None
    if selected:
        burndown = burndown_data(selected)
        rows = db.execute(
            """SELECT COALESCE(u.name, 'Unassigned') AS name,
                      SUM(CASE WHEN t.status!='done' THEN t.points ELSE 0 END) AS open_pts,
                      SUM(CASE WHEN t.status='done' THEN t.points ELSE 0 END) AS done_pts
               FROM tasks t LEFT JOIN users u ON u.id=t.assignee_id
               WHERE t.sprint_id=? GROUP BY t.assignee_id ORDER BY (u.name IS NULL), u.name""",
            (selected["id"],)).fetchall()
        workload = {"labels": [r["name"] for r in rows],
                    "open": [r["open_pts"] for r in rows],
                    "done": [r["done_pts"] for r in rows]}
        if selected["status"] == "active":
            days_left = (date.fromisoformat(selected["end_date"]) - date.today()).days

    finished = db.execute(
        "SELECT * FROM sprints WHERE project_id=? AND status='completed' ORDER BY completed_at",
        (pid,)).fetchall()
    velocity = {"labels": [s["name"] for s in finished],
                "committed": [s["committed_points"] for s in finished],
                "completed": [s["completed_points"] for s in finished]}
    return render_template("reports.html", project=project, role=role, tab="reports",
                           sprints=sprints, selected=selected, burndown=burndown,
                           workload=workload, velocity=velocity, days_left=days_left,
                           avg_velocity=average_velocity(pid))


# ---------------------------------------------------------------- errors
@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
def handle_error(err):
    if request.path.startswith("/api/"):
        return jsonify(ok=False, error=err.name), err.code
    messages = {403: "You do not have permission to do that in this project.",
                404: "That page does not exist."}
    return render_template("error.html", code=err.code,
                           message=messages.get(err.code, err.description)), err.code


init_db()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=int(os.environ.get("PORT", 5000)))
