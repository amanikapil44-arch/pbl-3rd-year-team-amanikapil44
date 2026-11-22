"""Simulated resource manager: tracks CPU, RAM, GPU and storage per worker.

All mutating functions expect to be called INSIDE a database transaction (db.transaction()),
so 'check availability' and 'allocate' are one atomic step. The CHECK constraints in the
schema are a second safety net: the database itself refuses negative availability.
Phase 3 hooks: locks/semaphores, Banker's algorithm, multi-worker selection.
"""
RESOURCE_TYPES = ("CPU", "RAM", "GPU", "STORAGE")
UNITS = {"CPU": "cores", "RAM": "GB", "GPU": "units", "STORAGE": "GB"}


def job_demand(job):
    return {"CPU": job["cpu_required"], "RAM": job["ram_required"],
            "GPU": job["gpu_required"], "STORAGE": job["storage_required"]}


def _worker_resources(conn, worker_id):
    rows = conn.execute("SELECT resource_type, total, available FROM resources WHERE worker_id=?",
                        (worker_id,)).fetchall()
    return {r["resource_type"]: {"total": r["total"], "available": r["available"]} for r in rows}


def max_capacity(conn):
    """Largest single-worker capacity per type (a job must fit on one worker)."""
    cap = {t: 0 for t in RESOURCE_TYPES}
    for r in conn.execute("""SELECT r.resource_type, MAX(r.total) m FROM resources r
                             JOIN workers w ON w.id = r.worker_id WHERE w.status='ACTIVE'
                             GROUP BY r.resource_type"""):
        cap[r["resource_type"]] = r["m"]
    return cap


def find_worker(conn, demand):
    """First-fit worker selection among ACTIVE workers. Returns worker id or None."""
    for w in conn.execute("SELECT id FROM workers WHERE status='ACTIVE' ORDER BY id").fetchall():
        res = _worker_resources(conn, w["id"])
        if all(res[t]["available"] >= demand[t] for t in RESOURCE_TYPES):
            return w["id"]
    return None


def shortage_reason(conn, demand):
    best = {t: 0 for t in RESOURCE_TYPES}
    for w in conn.execute("SELECT id FROM workers WHERE status='ACTIVE'").fetchall():
        res = _worker_resources(conn, w["id"])
        for t in RESOURCE_TYPES:
            best[t] = max(best[t], res[t]["available"])
    short = [f"{t} needs {demand[t]} (free {best[t]})" for t in RESOURCE_TYPES if demand[t] > best[t]]
    return "Insufficient resources: " + ", ".join(short) if short else "No suitable worker"


def allocate(conn, job, worker_id, now):
    """Reserve resources for a job. Returns True on success, False if insufficient."""
    demand = job_demand(job)
    res = _worker_resources(conn, worker_id)
    if any(res[t]["available"] < demand[t] for t in RESOURCE_TYPES):
        return False
    for t in RESOURCE_TYPES:
        conn.execute("UPDATE resources SET available = available - ? WHERE worker_id=? AND resource_type=?",
                     (demand[t], worker_id, t))
    conn.execute("""INSERT INTO allocations (job_id, worker_id, cpu, ram, gpu, storage, allocated_at)
                    VALUES (?,?,?,?,?,?,?)""",
                 (job["id"], worker_id, demand["CPU"], demand["RAM"], demand["GPU"], demand["STORAGE"], now))
    return True


def release(conn, job_id, now):
    """Return a job's resources to its worker. Idempotent: returns False if nothing was held."""
    rows = conn.execute("SELECT * FROM allocations WHERE job_id=? AND released_at IS NULL", (job_id,)).fetchall()
    for a in rows:
        for t, col in (("CPU", "cpu"), ("RAM", "ram"), ("GPU", "gpu"), ("STORAGE", "storage")):
            conn.execute("UPDATE resources SET available = available + ? WHERE worker_id=? AND resource_type=?",
                         (a[col], a["worker_id"], t))
        conn.execute("UPDATE allocations SET released_at=? WHERE id=?", (now, a["id"]))
    return bool(rows)


def utilization(conn):
    """Aggregate usage across ACTIVE workers: {type: {total, available, used, percent, unit}}."""
    out = {t: {"total": 0, "available": 0, "used": 0, "percent": 0, "unit": UNITS[t]} for t in RESOURCE_TYPES}
    for r in conn.execute("""SELECT r.resource_type t, SUM(r.total) total, SUM(r.available) available
                             FROM resources r JOIN workers w ON w.id=r.worker_id
                             WHERE w.status='ACTIVE' GROUP BY r.resource_type"""):
        o = out[r["t"]]
        o["total"], o["available"] = r["total"], r["available"]
        o["used"] = r["total"] - r["available"]
        o["percent"] = round(100 * o["used"] / r["total"]) if r["total"] else 0
    return out


def worker_summary(conn):
    workers = []
    for w in conn.execute("SELECT * FROM workers ORDER BY id").fetchall():
        res = _worker_resources(conn, w["id"])
        running = conn.execute("SELECT COUNT(*) FROM jobs WHERE worker_id=? AND status='Running'",
                               (w["id"],)).fetchone()[0]
        workers.append({"id": w["id"], "name": w["name"], "status": w["status"],
                        "resources": res, "running_jobs": running})
    return workers


def verify_consistency(conn):
    """Audit: available == total - active allocations, and Running <=> has active allocation."""
    problems = []
    for w in conn.execute("SELECT id, name FROM workers").fetchall():
        res = _worker_resources(conn, w["id"])
        used = conn.execute("""SELECT COALESCE(SUM(cpu),0) c, COALESCE(SUM(ram),0) r,
                               COALESCE(SUM(gpu),0) g, COALESCE(SUM(storage),0) s
                               FROM allocations WHERE worker_id=? AND released_at IS NULL""",
                            (w["id"],)).fetchone()
        for t, u in (("CPU", used["c"]), ("RAM", used["r"]), ("GPU", used["g"]), ("STORAGE", used["s"])):
            if res[t]["total"] - u != res[t]["available"]:
                problems.append(f"{w['name']} {t}: available={res[t]['available']} but total-used={res[t]['total'] - u}")
    for j in conn.execute("""SELECT j.id, j.status,
             (SELECT COUNT(*) FROM allocations a WHERE a.job_id=j.id AND a.released_at IS NULL) AS held
             FROM jobs j""").fetchall():
        if j["status"] == "Running" and j["held"] != 1:
            problems.append(f"Job {j['id']} is Running but holds {j['held']} allocations")
        if j["status"] != "Running" and j["held"] != 0:
            problems.append(f"Job {j['id']} is {j['status']} but still holds resources")
    return problems
