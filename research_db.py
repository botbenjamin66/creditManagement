import os, re, sqlite3, hashlib, base64, urllib.request, urllib.parse
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

ARCHIVE_DIR = Path(os.environ.get(
    "RESEARCH_ARCHIVE", r"Q:\00_pm\1_research\3_issuerCreditResearch\_sources"))
DB_PATH = ARCHIVE_DIR / "research_index.sqlite"
_UA = "nordIX-CreditPlatform/1.0 (internal research archive)"
_MAX_DL     = int(os.environ.get("RESEARCH_MAX_DOWNLOADS", "12"))
_DL_TIMEOUT = int(os.environ.get("RESEARCH_DL_TIMEOUT", "8"))
_DL_ENABLED = os.environ.get("RESEARCH_DOWNLOAD", "1") != "0"
_RUN_COLS = ("run_id", "ts", "kind", "mode", "issuer", "as_of", "verify_note")
_SRC_COLS = ("url", "title", "kind", "local_path", "ts")


def _conn():
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH))
    c.execute("CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY, ts TEXT, "
              "kind TEXT, mode TEXT, issuer TEXT, as_of TEXT, verify_note TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS sources(id INTEGER PRIMARY KEY AUTOINCREMENT, "
              "run_id TEXT, url TEXT, title TEXT, kind TEXT, local_path TEXT, ts TEXT)")
    return c


def new_run_id(issuer):
    slug = re.sub(r"[^A-Za-z0-9]+", "-", issuer or "issuer").strip("-")[:40] or "issuer"
    return datetime.now().strftime("%Y%m%d_%H%M%S_") + slug


def _attr(item, key):
    return item.get(key) if isinstance(item, dict) else getattr(item, key, None)


def extract_search_results(msg):
    out, seen = [], set()
    for b in getattr(msg, "content", []) or []:
        if _attr(b, "type") != "web_search_tool_result":
            continue
        for item in _attr(b, "content") or []:
            url = _attr(item, "url")
            if not url or url in seen:
                continue
            seen.add(url)
            out.append({"url": url, "title": _attr(item, "title") or url, "kind": "web"})
    return out


def _safe_name(url):
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    tail = urllib.parse.urlparse(url).path.rsplit("/", 1)[-1] or "doc"
    return h + "_" + (re.sub(r"[^A-Za-z0-9._-]+", "_", tail)[:60].strip("_") or "doc")


def archive_document(url, run_dir, timeout=_DL_TIMEOUT):
    if not url or urllib.parse.urlparse(url).scheme not in ("http", "https"):
        return None
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        name = _safe_name(url)
        for existing in run_dir.glob(name + "*"):
            return str(existing)
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            ctype = (r.headers.get("Content-Type") or "").lower()
            data = r.read(8 * 1024 * 1024)
        dest = run_dir / name
        ext = ".pdf" if "pdf" in ctype else (".html" if "html" in ctype else "")
        if ext and not dest.suffix:
            dest = dest.with_suffix(ext)
        dest.write_bytes(data)
        return str(dest)
    except Exception:
        return None


def _save_attachment(run_dir, att):
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        uri = att.get("data", "")
        dest = run_dir / re.sub(r"[^A-Za-z0-9._-]+", "_", att.get("name", "attachment"))
        dest.write_bytes(base64.b64decode(uri.split(",", 1)[1] if "," in uri else uri))
        return str(dest)
    except Exception:
        return None


def store_run(run_id, kind, mode, issuer, as_of, sources,
              attachments=None, verify_note="", download=None):
    download = _DL_ENABLED if download is None else download
    try:
        run_dir = ARCHIVE_DIR / run_id
        targets = [s for s in (sources or []) if s.get("url")][:_MAX_DL] if download else []
        paths = {}
        if targets:
            with ThreadPoolExecutor(max_workers=6) as pool:
                for s, p in zip(targets, pool.map(
                        lambda s: archive_document(s["url"], run_dir), targets)):
                    paths[s["url"]] = p
        now = datetime.now().isoformat(timespec="seconds")
        c = _conn()
        c.execute("INSERT OR REPLACE INTO runs VALUES(?,?,?,?,?,?,?)",
                  (run_id, now, kind, mode, issuer, as_of or "", verify_note or ""))
        enriched = []
        for s in (sources or []):
            local = paths.get(s.get("url"))
            c.execute("INSERT INTO sources(run_id,url,title,kind,local_path,ts) VALUES(?,?,?,?,?,?)",
                      (run_id, s.get("url", ""), s.get("title", ""), s.get("kind", "web"), local or "", now))
            enriched.append({**s, "local_path": local})
        for att in (attachments or []):
            p = _save_attachment(run_dir, att)
            c.execute("INSERT INTO sources(run_id,url,title,kind,local_path,ts) VALUES(?,?,?,?,?,?)",
                      (run_id, "", att.get("name", "attachment"), "attachment", p or "", now))
            enriched.append({"url": "", "title": att.get("name", "attachment"),
                             "kind": "attachment", "local_path": p})
        c.commit()
        c.close()
        return enriched
    except Exception as ex:
        print(f"[research_db] store_run failed: {ex}")
        return sources or []


def list_runs(limit=200):
    try:
        c = _conn()
        rows = c.execute("SELECT run_id,ts,kind,mode,issuer,as_of,verify_note FROM runs "
                         "ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
        c.close()
        return [dict(zip(_RUN_COLS, r)) for r in rows]
    except Exception:
        return []


def run_sources(run_id):
    try:
        c = _conn()
        rows = c.execute("SELECT url,title,kind,local_path,ts FROM sources "
                         "WHERE run_id=? ORDER BY id", (run_id,)).fetchall()
        c.close()
        return [dict(zip(_SRC_COLS, r)) for r in rows]
    except Exception:
        return []


def doc_rel(local_path):
    if not local_path:
        return None
    try:
        return str(Path(local_path).relative_to(ARCHIVE_DIR)).replace("\\", "/")
    except Exception:
        return None
