import threading, uuid, time

_JOBS = {}
_LOCK = threading.Lock()
_TTL = 1800


def start(fn, *args, **kwargs):
    jid = uuid.uuid4().hex[:12]
    with _LOCK:
        _JOBS[jid] = {"status": "running", "progress": "Starting", "result": None,
                      "error": None, "ts": time.time()}

    def _progress(msg):
        with _LOCK:
            if jid in _JOBS:
                _JOBS[jid]["progress"] = msg

    def _run():
        try:
            res = fn(*args, progress=_progress, **kwargs)
            with _LOCK:
                if jid in _JOBS:
                    _JOBS[jid].update(status="done", result=res, progress="Done")
        except Exception as ex:
            with _LOCK:
                if jid in _JOBS:
                    _JOBS[jid].update(status="error", error=str(ex), progress="Error")

    threading.Thread(target=_run, daemon=True).start()
    return jid


def poll(jid):
    with _LOCK:
        j = _JOBS.get(jid)
        out = dict(j) if j else None
    _sweep()
    return out


def cleanup(jid):
    with _LOCK:
        _JOBS.pop(jid, None)


def _sweep():
    now = time.time()
    with _LOCK:
        for k in [k for k, v in _JOBS.items()
                  if v["status"] != "running" and now - v["ts"] > _TTL]:
            _JOBS.pop(k, None)
