import sqlite3
import time
from contextlib import contextmanager

class Busy(Exception):
    pass

class InvalidLease(Exception):
    pass

class Engine:
    def __init__(self, path="turnstile.db", clock=time.time):
        self.path, self.clock = path, clock
        with self.connection() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS leases (
                resource TEXT PRIMARY KEY, owner TEXT NOT NULL,
                token INTEGER NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS values_demo (
                resource TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY, at REAL, kind TEXT,
                resource TEXT, owner TEXT, token INTEGER);
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise

    def event(self, db, kind, resource, owner, token):
        db.execute("INSERT INTO events(at,kind,resource,owner,token) VALUES(?,?,?,?,?)",
                   (self.clock(), kind, resource, owner, token))

    def acquire(self, resource, owner, ttl=5):
        with self.transaction() as db:
            now = self.clock()
            row = db.execute("SELECT * FROM leases WHERE resource=?", (resource,)).fetchone()
            if row and row['expires'] > now:
                raise Busy("Resource already leased; wait and retry")
            token = row['token'] + 1 if row else 1
            expires = now + ttl
            db.execute("INSERT OR REPLACE INTO leases VALUES(?,?,?,?)",
                       (resource, owner, token, expires))
            self.event(db, 'acquire', resource, owner, token)
            return dict(resource=resource, owner=owner, token=token, expires=expires)

    def check(self, db, resource, owner, token):
        row = db.execute("SELECT * FROM leases WHERE resource=?", (resource,)).fetchone()
        if not row or row['owner'] != owner or row['token'] != token or row['expires'] <= self.clock():
            raise InvalidLease("Lease expired, released, or replaced")

    def release(self, resource, owner, token):
        with self.transaction() as db:
            self.check(db, resource, owner, token)
            db.execute("UPDATE leases SET expires=0 WHERE resource=?", (resource,))
            self.event(db, 'release', resource, owner, token)
            return {'released': True}

    def write_demo(self, resource, owner, token, value):
        with self.transaction() as db:
            self.check(db, resource, owner, token)
            db.execute("INSERT OR REPLACE INTO values_demo VALUES(?,?)", (resource, value))
            self.event(db, 'write', resource, owner, token)
            return {'written': True, 'value': value}

    def events(self):
        with self.connection() as db:
            return [dict(r) for r in db.execute("SELECT * FROM events ORDER BY id DESC LIMIT 100")]
