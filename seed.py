"""Optional: insert sample jobs so the dashboard has something to show.  Run:  python seed.py"""
import validators
from database import db, repository

SAMPLES = [
    ("Data preprocessing", 3, 4, 4, 0, 20, 8),
    ("Model training", 9, 6, 8, 1, 50, 12),
    ("Log analysis", 5, 2, 2, 0, 10, 5),
    ("Image rendering", 7, 4, 6, 1, 40, 10),
    ("Backup task", 1, 2, 2, 0, 30, 4),
    ("Report generation", 5, 2, 4, 0, 5, 6),
]

if __name__ == "__main__":
    db.init_db()
    cap = repository.get_capacity()
    for name, prio, cpu, ram, gpu, storage, burst in SAMPLES:
        clean, errors = validators.validate_job(
            {"username": "demo_user", "name": name, "description": "Sample job", "priority": prio,
             "cpu_required": cpu, "ram_required": ram, "gpu_required": gpu,
             "storage_required": storage, "burst_time": burst}, cap)
        assert not errors, errors
        print("Created job", repository.create_job(clean), name)
