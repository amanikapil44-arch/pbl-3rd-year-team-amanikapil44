"""Flask application: routes for the web UI and a small JSON API."""
import datetime
import time

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for

import config
import validators
from database import db, repository
from execution import engine
from scheduler import algorithms, job_scheduler


def describe_cycle(s):
    parts = []
    if s["completed"]:
        parts.append("completed " + ", ".join(f"#{i}" for i in s["completed"]))
    if s["admitted"]:
        parts.append("queued " + ", ".join(f"#{i}" for i in s["admitted"]))
    if s["dispatched"]:
        parts.append("dispatched " + ", ".join(f"#{i}" for i in s["dispatched"]))
    if s["delayed"]:
        parts.append(f"job #{s['delayed']} waiting for resources")
    return f"Scheduler cycle ({s['algorithm']}): " + ("; ".join(parts) if parts else "nothing to do")


def create_app():
    app = Flask(__name__)
    app.secret_key = config.SECRET_KEY
    db.init_db()

    @app.template_filter("ts")
    def ts(value):
        return datetime.datetime.fromtimestamp(value).strftime("%H:%M:%S") if value else "—"

    @app.context_processor
    def inject_globals():
        return {"algorithms": algorithms.ALGORITHMS, "current_algorithm": repository.get_setting("algorithm")}

    # ---------- pages ----------
    @app.route("/")
    def dashboard():
        return render_template("dashboard.html", stats=repository.get_stats())

    @app.route("/submit", methods=["GET", "POST"])
    def submit():
        capacity = repository.get_capacity()
        if request.method == "POST":
            clean, errors = validators.validate_job(request.form, capacity)
            if errors:
                return render_template("submit.html", form=request.form, errors=errors, capacity=capacity), 400
            job_id = repository.create_job(clean)
            flash(f"Job #{job_id} submitted (status: Pending).", "success")
            return redirect(url_for("job_detail", job_id=job_id))
        return render_template("submit.html", form={"username": "demo_user", "priority": 5, "gpu_required": 0},
                               errors={}, capacity=capacity)

    @app.route("/jobs")
    def jobs():
        status = request.args.get("status")
        if status not in repository.STATUSES:
            status = None
        return render_template("jobs.html", jobs=repository.list_jobs(status), status=status,
                               statuses=repository.STATUSES)

    @app.route("/jobs/<int:job_id>")
    def job_detail(job_id):
        job = repository.get_job(job_id)
        if job is None:
            return render_template("job_detail.html", job=None), 404
        return render_template("job_detail.html", job=job, logs=repository.get_job_logs(job_id),
                               allocations=repository.get_job_allocations(job_id))

    @app.route("/jobs/<int:job_id>/fail", methods=["POST"])
    def fail_job(job_id):
        if engine.fail_job(job_id, "Simulated worker error", time.time()):
            flash(f"Job #{job_id} marked Failed; resources released.", "warning")
        else:
            flash("Only Running jobs can be failed.", "error")
        return redirect(url_for("job_detail", job_id=job_id))

    @app.route("/scheduler/run", methods=["POST"])
    def run_scheduler():
        flash(describe_cycle(job_scheduler.run_cycle()), "info")
        return redirect(request.referrer or url_for("dashboard"))

    @app.route("/scheduler/algorithm", methods=["POST"])
    def set_algorithm():
        name = request.form.get("algorithm", "")
        try:
            repository.set_algorithm(name)
            flash(f"Scheduling algorithm set to {name}.", "success")
        except ValueError as e:
            flash(str(e), "error")
        return redirect(url_for("dashboard"))

    @app.route("/admin/reset", methods=["POST"])
    def reset():
        repository.reset_all_jobs()
        flash("All jobs cleared and resources restored.", "warning")
        return redirect(url_for("dashboard"))

    # ---------- JSON API ----------
    @app.route("/api/stats")
    def api_stats():
        return jsonify(repository.get_stats())

    @app.route("/api/jobs", methods=["GET", "POST"])
    def api_jobs():
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            clean, errors = validators.validate_job(data, repository.get_capacity())
            if errors:
                return jsonify({"errors": errors}), 400
            return jsonify({"id": repository.create_job(clean), "status": "Pending"}), 201
        return jsonify(repository.list_jobs(request.args.get("status")))

    @app.route("/api/cycle", methods=["POST"])
    def api_cycle():
        return jsonify(job_scheduler.run_cycle())

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=False)
