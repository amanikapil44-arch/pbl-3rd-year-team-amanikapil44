"""Dedicated scheduler process for deployments using Gunicorn."""
import time
import app

if __name__ == '__main__':
    app.init_db()
    app.start_scheduler()
    while True:
        time.sleep(3600)
