import os, re, json, sqlite3
from datetime import datetime, timedelta
import research_db

DB_PATH = research_db.ARCHIVE_DIR / "analysis_store.sqlite"
CACHE_TTL_HOURS = int(os.environ.get("CREDIT_CACHE_TTL_H", "672"))
_COLS = ("id", "ts", "kind", "mode", "issuer", "verify_note")


def _key(issuer):
    return re.sub(r"\s+", " ", (issuer or "").strip().lower())


def _conn():
    research_db.ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH))
    c.execute("CREATE TABLE IF NOT EXISTS analyses(id INTEGER PRIMARY KEY AUTOINCREMENT, "
              "ts TEXT, kind TEXT, mode TEXT, issuer TEXT, issuer_key TEXT, as_of TEXT, "
              "run_id TEXT, verify_note TEXT, data TEXT)")
    return c


def save_analysis(kind, mode, issuer, data):
    try:
        c = _conn()
        cur = c.execute(
            "INSERT INTO analyses(ts,kind,mode,issuer,issuer_key,as_of,run_id,verify_note,data) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (datetime.now().isoformat(timespec="seconds"), kind, mode, issuer, _key(issuer),
             data.get("as_of", ""), data.get("_run_id", ""), data.get("_verify_overall", ""),
             json.dumps(data, ensure_ascii=False)))
        c.commit()
        rid = cur.lastrowid
        c.close()
        return rid
    except Exception as ex:
        print(f"[analysis_db] save failed: {ex}")
        return None


def recent_analysis(issuer, mode, ttl_hours=CACHE_TTL_HOURS):
    try:
        c = _conn()
        row = c.execute("SELECT ts,data FROM analyses WHERE issuer_key=? AND mode=? "
                        "ORDER BY ts DESC LIMIT 1", (_key(issuer), mode)).fetchone()
        c.close()
        if not row:
            return None
        if datetime.now() - datetime.fromisoformat(row[0]) > timedelta(hours=ttl_hours):
            return None
        return json.loads(row[1])
    except Exception:
        return None


def list_analyses(limit=60, kind=None):
    try:
        c = _conn()
        if kind:
            rows = c.execute("SELECT id,ts,kind,mode,issuer,verify_note FROM analyses "
                             "WHERE kind=? ORDER BY ts DESC LIMIT ?", (kind, limit)).fetchall()
        else:
            rows = c.execute("SELECT id,ts,kind,mode,issuer,verify_note FROM analyses "
                             "ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
        c.close()
        return [dict(zip(_COLS, r)) for r in rows]
    except Exception:
        return []


def get_analysis(aid):
    try:
        c = _conn()
        row = c.execute("SELECT data FROM analyses WHERE id=?", (aid,)).fetchone()
        c.close()
        return json.loads(row[0]) if row else None
    except Exception:
        return None
