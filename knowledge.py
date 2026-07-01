import os, re, hashlib
from pathlib import Path

KNOWLEDGE_DIR = Path(os.environ.get("KNOWLEDGE_DIR", str(Path(__file__).parent / "knowledge")))
SCOPES = ["corp", "fin", "sov", "prospectus", "market", "liquidity", "all"]
_MAX_CTX = int(os.environ.get("KNOWLEDGE_MAX_CHARS", "9000"))


def _dir():
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    return KNOWLEDGE_DIR


def _parse(path):
    try:
        txt = path.read_text(encoding="utf-8")
    except Exception:
        return None
    title, scope, body = path.stem, "", txt
    if "---" in txt:
        head, body = txt.split("---", 1)
        for line in head.splitlines():
            low = line.lower()
            if low.startswith("title:"):
                title = line.split(":", 1)[1].strip() or title
            elif low.startswith("scope:"):
                scope = line.split(":", 1)[1].strip()
    return {"id": path.name, "title": title, "scope": scope, "body": body.strip()}


def list_entries():
    try:
        return [e for e in (_parse(p) for p in sorted(_dir().glob("*.md"))) if e]
    except Exception:
        return []


def get_entry(fid):
    p = _dir() / fid
    return _parse(p) if (fid and p.exists()) else None


def _slug(title):
    return re.sub(r"[^A-Za-z0-9]+", "-", title or "note").strip("-").lower()[:50] or "note"


def save_entry(fid, title, scope, body):
    try:
        if not fid or fid == "__new__":
            fid = _slug(title) + "-" + hashlib.sha1((title + body).encode("utf-8")).hexdigest()[:6] + ".md"
        (_dir() / fid).write_text(f"title: {title}\nscope: {scope}\n---\n{body}\n", encoding="utf-8")
        return fid
    except Exception as ex:
        print(f"[knowledge] save failed: {ex}")
        return None


def delete_entry(fid):
    try:
        p = _dir() / fid
        if p.exists():
            p.unlink()
        return True
    except Exception:
        return False


def _scopes_of(e):
    return {s.strip().lower() for s in re.split(r"[,\s]+", e.get("scope", "")) if s.strip()}


def context_for(scope):
    parts = []
    for e in list_entries():
        sc = _scopes_of(e)
        if scope in sc or "all" in sc:
            parts.append(f"## {e['title']}\n{e['body']}")
    if not parts:
        return ""
    txt = "\n\n".join(parts)[:_MAX_CTX]
    return ("HOUSE ANALYTICAL FRAMEWORK - distilled from internal research. Apply these "
            "viewpoints, methods and red-flags throughout your analysis:\n\n" + txt + "\n\n")
