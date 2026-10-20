import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

SCHEMA = '''
CREATE TABLE IF NOT EXISTS projects (
 id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL, path TEXT UNIQUE NOT NULL,
 verify TEXT NOT NULL, context_paths TEXT NOT NULL, network INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS workflows (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), objective TEXT NOT NULL,
 request_key TEXT NOT NULL, status TEXT NOT NULL, phase TEXT NOT NULL, leader TEXT,
 generation INTEGER NOT NULL DEFAULT 0, complexity TEXT NOT NULL, calls INTEGER NOT NULL DEFAULT 0,
 max_calls INTEGER NOT NULL, repairs INTEGER NOT NULL DEFAULT 0, max_repairs INTEGER NOT NULL,
 next_run REAL NOT NULL DEFAULT 0, workspace TEXT, base_commit TEXT, delivery TEXT, plan TEXT NOT NULL DEFAULT '{}',
 review TEXT NOT NULL DEFAULT '{}', handoff TEXT NOT NULL DEFAULT '{}', verification TEXT NOT NULL DEFAULT '{}', summary TEXT NOT NULL DEFAULT '',
 error TEXT NOT NULL DEFAULT '', created REAL NOT NULL, updated REAL NOT NULL,
 UNIQUE(project_id, request_key));
CREATE TABLE IF NOT EXISTS attempts (
 id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL REFERENCES workflows(id), provider TEXT NOT NULL,
 phase TEXT NOT NULL, generation INTEGER NOT NULL, status TEXT NOT NULL, pid INTEGER,
 artifact TEXT NOT NULL, created REAL NOT NULL, ended REAL, outcome TEXT, error TEXT NOT NULL DEFAULT '',
 usage TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS health (
 provider TEXT PRIMARY KEY, until REAL NOT NULL DEFAULT 0, reason TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, workflow_id TEXT, kind TEXT NOT NULL, data TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS file_cache (
 path TEXT PRIMARY KEY, mtime_ns INTEGER NOT NULL, size INTEGER NOT NULL, sha256 TEXT NOT NULL, content TEXT NOT NULL, last_used REAL NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS memories (
 project_id TEXT NOT NULL REFERENCES projects(id), name TEXT NOT NULL, content TEXT NOT NULL,
 updated REAL NOT NULL, PRIMARY KEY(project_id, name));
'''
ACTIVE = ('queued', 'running', 'waiting', 'recovering')
TERMINAL = ('completed', 'blocked', 'cancelled', 'needs_review')


def encode(value):
    return json.dumps(value, ensure_ascii=False)


class Store:
    def __init__(self, home):
        self.home = Path(home).resolve()
        self.home.mkdir(parents=True, exist_ok=True)
        self.db_path = self.home / 'hub.sqlite3'
        with self.connection() as db:
            db.executescript(SCHEMA)
            columns = {row['name'] for row in db.execute('PRAGMA table_info(workflows)')}
            if 'handoff' not in columns:
                db.execute("ALTER TABLE workflows ADD COLUMN handoff TEXT NOT NULL DEFAULT '{}'")
            if 'delivery' not in columns:
                db.execute('ALTER TABLE workflows ADD COLUMN delivery TEXT')
            cache_columns = {row['name'] for row in db.execute('PRAGMA table_info(file_cache)')}
            if 'last_used' not in cache_columns:
                db.execute('ALTER TABLE file_cache ADD COLUMN last_used REAL NOT NULL DEFAULT 0')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.db_path, timeout=20)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def one(self, sql, params=()):
        with self.connection() as db:
            row = db.execute(sql, params).fetchone()
            return dict(row) if row else None

    def all(self, sql, params=()):
        with self.connection() as db:
            return [dict(r) for r in db.execute(sql, params).fetchall()]

    def workflow(self, workflow_id):
        item = self.one('SELECT * FROM workflows WHERE id=?', (workflow_id,))
        if not item:
            raise ValueError('Unknown workflow')
        return item

    def project(self, project):
        row = self.one('SELECT * FROM projects WHERE id=? OR name=?', (project, project))
        if not row:
            raise ValueError('Unknown project; register it first with project-add')
        return row

    def add_project(self, name, path, verify, context_paths, network=False, allow_unverified=False):
        path = Path(path).resolve()
        if not path.is_dir():
            raise ValueError('Project directory does not exist')
        if (not verify and not allow_unverified) or not isinstance(verify, list) or not all(isinstance(command, list) and command and
                                 all(isinstance(x, str) for x in command) for command in verify):
            raise ValueError('verify must contain executable argument arrays, never shell strings')
        for item in context_paths:
            candidate = (path / item).resolve()
            if not candidate.is_relative_to(path):
                raise ValueError('Context path must be inside the project')
        existing = self.one('SELECT * FROM projects WHERE name=?', (name,))
        if existing:
            if existing['path'] != str(path):
                raise ValueError('Project name already points to another folder')
            return existing
        project_id = uuid.uuid4().hex[:12]
        with self.connection() as db:
            db.execute('INSERT INTO projects VALUES(?,?,?,?,?,?)',
                       (project_id, name, str(path), encode(verify), encode(context_paths), int(network)))
        return self.project(project_id)

    def create(self, project, objective, request_key, complexity, max_calls, max_repairs):
        project = self.project(project)
        if not isinstance(objective, str) or not objective.strip() or len(objective) > 16000:
            raise ValueError('Objective must contain 1–16000 characters')
        if not request_key or len(request_key) > 160:
            raise ValueError('A nonempty request_key is required (max 160 characters)')
        now = time.time()
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM workflows WHERE project_id=? AND request_key=?',
                             (project['id'], request_key)).fetchone()
            if old:
                if old['objective'] != objective:
                    raise ValueError('request_key already belongs to a different objective')
                return dict(old)
            active = db.execute("SELECT id FROM workflows WHERE project_id=? AND status IN ('queued','running','waiting','recovering')",
                                (project['id'],)).fetchone()
            if active:
                raise ValueError('Project already has active workflow ' + active['id'])
            workflow_id = uuid.uuid4().hex[:12]
            phase = 'implement' if complexity == 'small' else 'plan'
            db.execute('''INSERT INTO workflows
                (id,project_id,objective,request_key,status,phase,complexity,max_calls,max_repairs,created,updated)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)''', (workflow_id, project['id'], objective, request_key,
                'queued', phase, complexity, max_calls, max_repairs, now, now))
            self._event(db, workflow_id, 'created', {'complexity': complexity, 'max_calls': max_calls})
        return self.workflow(workflow_id)

    def _event(self, db, workflow_id, kind, data):
        db.execute('INSERT INTO events(workflow_id,kind,data,created) VALUES(?,?,?,?)',
                   (workflow_id, kind, encode(data), time.time()))

    def update(self, workflow_id, expected_generation=None, **fields):
        allowed = {'status','phase','leader','generation','complexity','calls','max_calls','repairs',
                   'next_run','workspace','base_commit','delivery','plan','review','handoff','verification','summary','error'}
        if set(fields) - allowed:
            raise ValueError('Unknown state field')
        fields['updated'] = time.time()
        sql = 'UPDATE workflows SET ' + ','.join(k + '=?' for k in fields) + ' WHERE id=?'
        params = list(fields.values()) + [workflow_id]
        if fields.get('status') != 'cancelled':
            sql += " AND status != 'cancelled'"
        if expected_generation is not None:
            sql += " AND generation=? AND status NOT IN ('cancelled','blocked')"
            params.append(expected_generation)
        with self.connection() as db:
            return db.execute(sql, params).rowcount == 1

    def event(self, workflow_id, kind, data):
        with self.connection() as db:
            self._event(db, workflow_id, kind, data)

    def health(self, provider, until, reason):
        with self.connection() as db:
            db.execute('INSERT INTO health VALUES(?,?,?) ON CONFLICT(provider) DO UPDATE SET until=excluded.until,reason=excluded.reason',
                       (provider, until, reason))

    def remember(self, project_id, name, content):
        if len(content) > 30000 or len(name) > 100:
            raise ValueError('Memory is too large; summarize it first')
        with self.connection() as db:
            db.execute('INSERT INTO memories VALUES(?,?,?,?) ON CONFLICT(project_id,name) DO UPDATE SET content=excluded.content,updated=excluded.updated',
                       (project_id, name, content, time.time()))

    def cancel(self, workflow_id):
        with self.connection() as db:
            db.execute("UPDATE workflows SET status='cancelled',generation=generation+1,updated=? WHERE id=? AND status != 'completed'",
                       (time.time(), workflow_id))
            self._event(db, workflow_id, 'cancel_requested', {})
        return self.workflow(workflow_id)
