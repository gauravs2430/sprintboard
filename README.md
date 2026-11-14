# SprintBoard

A lightweight Agile/Scrum project management tool. Teams keep a product backlog, plan sprints, assign tasks, move them across a board, and track progress with burndown and velocity charts.

Built with Python (Flask), SQLite, and plain HTML/CSS/JavaScript. Chart.js and SortableJS are bundled in `static/vendor`, so the app runs without an internet connection.

## Run it

You need Python 3.9 or newer.

```
pip install -r requirements.txt
python seed.py        # optional: adds a demo project
python app.py
```

Open http://127.0.0.1:5000 in a browser. On Windows you can double-click `run_windows.bat` instead.

### Demo logins

After `python seed.py`, these accounts exist. The password for all of them is `demo123`.

| Email | Role in the demo project |
|---|---|
| asha@demo.com | Scrum Master |
| ravi@demo.com | Product Owner |
| meera@demo.com | Developer |
| karan@demo.com | Developer |

`python seed.py --reset` wipes the database and loads the demo data again. Demo dates are relative to the day you run it, so the active sprint is always mid-way.

## Features

| Screen | What it does |
|---|---|
| Sign up / Log in | Accounts with hashed passwords |
| Dashboard | Your projects, and the open tasks assigned to you |
| Backlog & Sprints | Add stories, tasks and bugs with priority and story points; drag to reorder; drag items into a sprint; create, start and complete sprints |
| Sprint Board | Drag cards between To Do, In Progress, In Review and Done |
| Task page | Edit details, assignee, due date, status and sprint; comments |
| Reports | Sprint burndown, velocity across sprints, workload per member |
| Team | Add members by email, change roles, remove members |

Scrum rules built in:

- Only one sprint can be active at a time.
- Completing a sprint records committed and completed points, and moves unfinished items to the top of the backlog.
- The planner warns when a sprint holds more points than the average velocity of the last three sprints.

### Roles

| Action | Scrum Master | Product Owner | Developer |
|---|---|---|---|
| Add, edit and move items; comment | Yes | Yes | Yes |
| Delete items | Yes | Yes | No |
| Create, start and complete sprints | Yes | No | No |
| Add or remove members, change roles | Yes | No | No |

Whoever creates a project becomes its Scrum Master and owner.

## Project structure

```
app.py              Flask app: routes, database schema, burndown logic
seed.py             Demo data
requirements.txt
static/
  style.css
  app.js            Drag-and-drop for the planner and the board
  vendor/           Chart.js and SortableJS
templates/          One HTML template per screen
```

## Database

SQLite file `sprintboard.db`, created automatically on first run.

| Table | Holds |
|---|---|
| users | name, email, password hash |
| projects | name, key, description, owner |
| members | which user is in which project, and their role |
| sprints | dates, goal, status, committed and completed points |
| tasks | title, type, priority, points, status, assignee, sprint, order |
| comments | task, author, text |

## How the charts are calculated

- **Burndown:** for each day of the sprint, remaining = total points in the sprint minus points of items marked Done on or before that day. The ideal line falls evenly from the total to zero. For an active sprint the total is the current scope, so adding an item mid-sprint raises the whole line.
- **Velocity:** points committed and completed in each finished sprint.
- **Workload:** done and open points per assignee in the selected sprint.

## Limits

- This is a development server for local use and demos. For real deployment, run it behind a production WSGI server such as Waitress or Gunicorn, with HTTPS.
- No email notifications and no password reset.
- A member must sign up before a Scrum Master can add them to a project.
