"""CloudFlow: Flask + SQLite multi-user job tracker (safe simulated execution)."""
import os, random, sqlite3, threading, time, secrets, fnmatch, re
from datetime import datetime, timezone
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, abort, jsonify, request, session

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get('CLOUDFLOW_DB', os.path.join(BASE, 'cloudflow.db'))
TICK_SECONDS = float(os.environ.get('CLOUDFLOW_TICK', '2'))
JOB_TYPES = ['Model Training', 'Data Processing', 'Image Analysis', 'Simulation', 'Batch Inference', 'Custom']
PRIORITIES = {'low': 0, 'normal': 1, 'high': 2}
app = Flask(__name__, static_folder='static', static_url_path='')
app.secret_key = os.environ.get('CLOUDFLOW_SECRET_KEY') or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE') == '1')
lock = threading.RLock()
_auth_attempts = {}


def conn():
    c = sqlite3.connect(DB, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c

def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def row(r): return dict(r) if r else None

def init_db():
    with lock, conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS workers(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,cpu_total INTEGER NOT NULL,ram_total INTEGER NOT NULL,gpu_total INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER REFERENCES users(id),name TEXT NOT NULL,type TEXT NOT NULL,status TEXT NOT NULL,priority TEXT NOT NULL DEFAULT 'normal',cpu INTEGER NOT NULL,ram INTEGER NOT NULL,gpu INTEGER NOT NULL,command TEXT DEFAULT '',progress INTEGER NOT NULL DEFAULT 0,worker_id INTEGER,created_at TEXT NOT NULL,started_at TEXT,finished_at TEXT,retry_count INTEGER NOT NULL DEFAULT 0,auto_retry INTEGER NOT NULL DEFAULT 0,max_retries INTEGER NOT NULL DEFAULT 2,workflow_id TEXT,step_order INTEGER,depends_on_job_id INTEGER);
        CREATE TABLE IF NOT EXISTS logs(id INTEGER PRIMARY KEY AUTOINCREMENT,job_id INTEGER NOT NULL REFERENCES jobs(id),ts TEXT NOT NULL,line TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS samples(ts TEXT NOT NULL,cpu REAL NOT NULL,ram REAL NOT NULL,gpu REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL REFERENCES users(id),job_id INTEGER NOT NULL,message TEXT NOT NULL,created_at TEXT NOT NULL,read INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS workflows(id TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),name TEXT NOT NULL,created_at TEXT NOT NULL);
        ''')
        # Migrate databases created by earlier CloudFlow versions.
        cols = {r['name'] for r in c.execute('PRAGMA table_info(jobs)')}
        if 'user_id' not in cols: c.execute('ALTER TABLE jobs ADD COLUMN user_id INTEGER REFERENCES users(id)')
        if 'retry_count' not in cols: c.execute('ALTER TABLE jobs ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0')
        for col, ddl in [('auto_retry','INTEGER NOT NULL DEFAULT 0'),('max_retries','INTEGER NOT NULL DEFAULT 2'),('workflow_id','TEXT'),('step_order','INTEGER'),('depends_on_job_id','INTEGER')]:
            if col not in cols: c.execute(f'ALTER TABLE jobs ADD COLUMN {col} {ddl}')
        c.executescript('CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status); CREATE INDEX IF NOT EXISTS idx_jobs_user_created ON jobs(user_id,created_at); CREATE INDEX IF NOT EXISTS idx_logs_job ON logs(job_id); CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id,read); CREATE INDEX IF NOT EXISTS idx_jobs_dependency ON jobs(depends_on_job_id,status);')
        if c.execute('SELECT COUNT(*) FROM workers').fetchone()[0] == 0:
            c.executemany('INSERT INTO workers(name,cpu_total,ram_total,gpu_total) VALUES (?,?,?,?)', [('worker-1',16,64,0),('worker-2',32,128,2),('worker-3',64,256,2)])

def log(c, job_id, line): c.execute('INSERT INTO logs(job_id,ts,line) VALUES (?,?,?)',(job_id,now(),line))
def notify(c, user_id, job_id, message):
    if user_id: c.execute('INSERT INTO notifications(user_id,job_id,message,created_at) VALUES (?,?,?,?)',(user_id,job_id,message,now()))

def login_required(fn):
    @wraps(fn)
    def wrapped(*a, **kw):
        if not session.get('user_id'): return jsonify(error='Please log in'), 401
        return fn(*a, **kw)
    return wrapped

def csrf_protect(fn):
    @wraps(fn)
    def wrapped(*a, **kw):
        if request.method not in ('GET','HEAD','OPTIONS'):
            token = session.get('csrf_token')
            if not token or request.headers.get('X-CSRF-Token') != token: return jsonify(error='Invalid CSRF token'), 403
        return fn(*a, **kw)
    return wrapped

@app.before_request
def ensure_db(): init_db()

@app.after_request
def security_headers(resp):
    resp.headers['X-Content-Type-Options']='nosniff'; resp.headers['X-Frame-Options']='DENY'; resp.headers['Referrer-Policy']='same-origin'
    return resp

@app.get('/')
def index(): return app.send_static_file('index.html')

@app.get('/api/auth/me')
def auth_me():
    if not session.get('user_id'): return jsonify(authenticated=False)
    return jsonify(authenticated=True, username=session.get('username'), csrf_token=session.get('csrf_token'))

@app.post('/api/auth/register')
def register():
    d=request.get_json(silent=True) or {}; username=str(d.get('username','')).strip().lower(); password=str(d.get('password',''))
    if not 3 <= len(username) <= 32 or not username.replace('_','').isalnum(): return jsonify(error='Username must be 3–32 letters, numbers or underscores'),400
    if len(password)<10: return jsonify(error='Password must be at least 10 characters'),400
    ip=request.remote_addr or 'unknown'; stamp=time.time(); attempts=[t for t in _auth_attempts.get(ip,[]) if stamp-t<300]
    if len(attempts)>=10: return jsonify(error='Too many attempts. Try again in five minutes.'),429
    _auth_attempts[ip]=attempts+[stamp]
    try:
        with conn() as c: cur=c.execute('INSERT INTO users(username,password_hash,created_at) VALUES (?,?,?)',(username,generate_password_hash(password),now()))
    except sqlite3.IntegrityError: return jsonify(error='Username is already taken'),409
    session.clear(); session['user_id']=cur.lastrowid; session['username']=username; session['csrf_token']=secrets.token_urlsafe(32)
    return jsonify(authenticated=True,username=username,csrf_token=session['csrf_token']),201

@app.post('/api/auth/login')
def login():
    d=request.get_json(silent=True) or {}; username=str(d.get('username','')).strip().lower(); password=str(d.get('password',''))
    ip=request.remote_addr or 'unknown'; stamp=time.time(); attempts=[t for t in _auth_attempts.get(ip,[]) if stamp-t<300]
    if len(attempts)>=10: return jsonify(error='Too many attempts. Try again in five minutes.'),429
    _auth_attempts[ip]=attempts+[stamp]
    with conn() as c: u=c.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
    if not u or not check_password_hash(u['password_hash'],password): return jsonify(error='Invalid username or password'),401
    session.clear(); session['user_id']=u['id']; session['username']=u['username']; session['csrf_token']=secrets.token_urlsafe(32)
    return jsonify(authenticated=True,username=u['username'],csrf_token=session['csrf_token'])

@app.post('/api/auth/logout')
@login_required
@csrf_protect
def logout(): session.clear(); return jsonify(ok=True)

# Scheduler is a single-process simulator. It never executes user-provided shell commands.
def worker_usage(c):
    return {r['worker_id']:(r['cpu'] or 0,r['ram'] or 0,r['gpu'] or 0) for r in c.execute("SELECT worker_id,SUM(cpu) cpu,SUM(ram) ram,SUM(gpu) gpu FROM jobs WHERE status='running' AND worker_id IS NOT NULL GROUP BY worker_id")}

def tick():
    with lock, conn() as c:
        retried_ids=[]
        for j in c.execute("SELECT * FROM jobs WHERE status='running'").fetchall():
            prog=min(100,j['progress']+random.randint(4,9))
            if prog>=100:
                failed=random.random()<0.08
                if failed and j['auto_retry'] and j['retry_count'] < j['max_retries']:
                    c.execute("UPDATE jobs SET status='pending',progress=0,worker_id=NULL,started_at=NULL,retry_count=retry_count+1 WHERE id=?",(j['id'],))
                    retried_ids.append(j['id'])
                    log(c,j['id'],f"Attempt failed; automatic recovery queued retry {j['retry_count']+1}/{j['max_retries']}")
                    notify(c,j['user_id'],j['id'],f"Job {j['name']} failed; retry {j['retry_count']+1} queued")
                else:
                    status='failed' if failed else 'completed'
                    c.execute('UPDATE jobs SET status=?,progress=?,finished_at=? WHERE id=?',(status,min(prog,99) if failed else 100,now(),j['id']))
                    log(c,j['id'],'ERROR: simulated process exited with code 1' if failed else 'Job completed successfully')
                    notify(c,j['user_id'],j['id'],f"Job {j['name']} {status}")
            else:
                c.execute('UPDATE jobs SET progress=? WHERE id=?',(prog,j['id']))
                if prog//25>j['progress']//25: log(c,j['id'],f'Progress {prog}%')
        workers=c.execute('SELECT * FROM workers').fetchall(); usage=worker_usage(c)
        pending=c.execute("SELECT * FROM jobs j WHERE j.status='pending' AND (j.depends_on_job_id IS NULL OR EXISTS (SELECT 1 FROM jobs d WHERE d.id=j.depends_on_job_id AND d.status='completed')) ORDER BY CASE j.priority WHEN 'high' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END,j.id").fetchall()
        pending=[j for j in pending if j['id'] not in retried_ids]
        blocked=c.execute("SELECT j.* FROM jobs j JOIN jobs d ON d.id=j.depends_on_job_id WHERE j.status='pending' AND d.status IN ('failed','cancelled')").fetchall()
        for b in blocked:
            c.execute("UPDATE jobs SET status='failed',finished_at=? WHERE id=?",(now(),b['id']))
            log(c,b['id'],f"Workflow stopped because dependency job #{b['depends_on_job_id']} did not complete")
            notify(c,b['user_id'],b['id'],f"Workflow step {b['name']} failed because its dependency did not complete")
        for j in pending:
            for w in workers:
                u=usage.get(w['id'],(0,0,0))
                if u[0]+j['cpu']<=w['cpu_total'] and u[1]+j['ram']<=w['ram_total'] and u[2]+j['gpu']<=w['gpu_total']:
                    c.execute("UPDATE jobs SET status='running',worker_id=?,started_at=?,progress=1 WHERE id=?",(w['id'],now(),j['id']))
                    log(c,j['id'],f"Allocated {j['cpu']} CPU / {j['ram']} GB RAM / {j['gpu']} GPU on {w['name']}"); log(c,j['id'],'Job started')
                    usage[w['id']]=(u[0]+j['cpu'],u[1]+j['ram'],u[2]+j['gpu']); break
        tot=c.execute('SELECT SUM(cpu_total) a,SUM(ram_total) b,SUM(gpu_total) g FROM workers').fetchone(); used=[sum(v[i] for v in usage.values()) for i in range(3)]
        pct=lambda u,t: round(100*u/t,1) if t else 0.0
        c.execute('INSERT INTO samples(ts,cpu,ram,gpu) VALUES (?,?,?,?)',(now(),pct(used[0],tot['a']),pct(used[1],tot['b']),pct(used[2],tot['g'])))
        c.execute('DELETE FROM samples WHERE rowid NOT IN (SELECT rowid FROM samples ORDER BY rowid DESC LIMIT 5000)')

def scheduler_loop():
    while True:
        try: tick()
        except Exception as e: app.logger.exception('scheduler error: %s',e)
        time.sleep(TICK_SECONDS)
_scheduler_started=False
def start_scheduler():
    global _scheduler_started
    if not _scheduler_started:
        _scheduler_started=True; threading.Thread(target=scheduler_loop,daemon=True,name='cloudflow-scheduler').start()

@app.get('/api/summary')
@login_required
def summary():
    uid=session['user_id']
    with conn() as c:
        counts={r['status']:r['n'] for r in c.execute('SELECT status,COUNT(*) n FROM jobs WHERE user_id=? GROUP BY status',(uid,))}
        recent=[row(r) for r in c.execute('SELECT id,name,status,progress FROM jobs WHERE user_id=? ORDER BY id DESC LIMIT 3',(uid,))]
    return jsonify(total=sum(counts.values()),running=counts.get('running',0),pending=counts.get('pending',0),completed=counts.get('completed',0),recent=recent)

@app.get('/api/jobs')
@login_required
def list_jobs():
    status=request.args.get('status','').strip(); q=request.args.get('q','').strip(); limit=min(100,max(1,request.args.get('limit',50,type=int))); offset=max(0,request.args.get('offset',0,type=int)); sort=request.args.get('sort','created_at'); direction='ASC' if request.args.get('order')=='asc' else 'DESC'
    if status and status not in ('pending','running','completed','failed','cancelled'): return jsonify(error='Invalid status'),400
    if sort not in ('id','name','status','priority','created_at','progress'): sort='created_at'
    sql='SELECT j.*,w.name worker FROM jobs j LEFT JOIN workers w ON w.id=j.worker_id WHERE j.user_id=?'; args=[session['user_id']]
    if status: sql+=' AND j.status=?'; args.append(status)
    if q:
        # instr() treats %, _ and backslashes as ordinary literal characters.
        sql+=" AND (instr(lower(j.name),lower(?))>0 OR instr(CAST(j.id AS TEXT),?)>0)"; args.extend([q,q])
    with conn() as c:
        total=c.execute('SELECT COUNT(*) FROM jobs j WHERE j.user_id=?'+(' AND j.status=?' if status else ''),([session['user_id'],status] if status else [session['user_id']])).fetchone()[0]
        jobs=[row(r) for r in c.execute(sql+f' ORDER BY j.{sort} {direction},j.id DESC LIMIT ? OFFSET ?',args+[limit,offset])]
    return jsonify(items=jobs,total=total,limit=limit,offset=offset)

@app.post('/api/jobs')
@login_required
@csrf_protect
def create_job():
    d=request.get_json(silent=True) or {}; name=str(d.get('name','')).strip(); typ=d.get('type','Custom'); prio=d.get('priority','normal'); auto_retry=1 if d.get('auto_retry') else 0
    try: max_retries=max(0,min(3,int(d.get('max_retries',2))))
    except (TypeError,ValueError): return jsonify(error='max_retries must be a whole number'),400
    try: cpu,ram,gpu=int(d.get('cpu',1)),int(d.get('ram',1)),int(d.get('gpu',0))
    except (TypeError,ValueError): return jsonify(error='cpu, ram and gpu must be whole numbers'),400
    if not name or len(name)>80: return jsonify(error='Job name is required (max 80 characters)'),400
    if typ not in JOB_TYPES: return jsonify(error='Unknown job type'),400
    if prio not in PRIORITIES: return jsonify(error='Priority must be low, normal or high'),400
    if not (1<=cpu<=64 and 1<=ram<=256 and 0<=gpu<=4): return jsonify(error='Resources out of range (CPU 1-64, RAM 1-256 GB, GPU 0-4)'),400
    with lock,conn() as c:
        workers=c.execute('SELECT * FROM workers').fetchall()
        if not any(cpu<=w['cpu_total'] and ram<=w['ram_total'] and gpu<=w['gpu_total'] for w in workers): return jsonify(error='No worker has enough total capacity for this resource request'),400
        cur=c.execute('INSERT INTO jobs(user_id,name,type,status,priority,cpu,ram,gpu,command,created_at,auto_retry,max_retries) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(session['user_id'],name,typ,'pending',prio,cpu,ram,gpu,str(d.get('command',''))[:500],now(),auto_retry,max_retries))
        log(c,cur.lastrowid,'Job submitted, waiting for a worker'); job=row(c.execute('SELECT * FROM jobs WHERE id=?',(cur.lastrowid,)).fetchone())
    return jsonify(job),201

@app.get('/api/jobs/<int:job_id>')
@login_required
def get_job(job_id):
    with conn() as c:
        j=c.execute('SELECT j.*,w.name worker FROM jobs j LEFT JOIN workers w ON w.id=j.worker_id WHERE j.id=? AND j.user_id=?',(job_id,session['user_id'])).fetchone()
        if not j: abort(404)
        out=row(j); out['logs']=[row(r) for r in c.execute('SELECT ts,line FROM logs WHERE job_id=? ORDER BY id',(job_id,))]
    return jsonify(out)

@app.post('/api/jobs/<int:job_id>/cancel')
@login_required
@csrf_protect
def cancel_job(job_id):
    with lock,conn() as c:
        j=c.execute('SELECT * FROM jobs WHERE id=? AND user_id=?',(job_id,session['user_id'])).fetchone()
        if not j: abort(404)
        if j['status'] not in ('pending','running'): return jsonify(error='Only pending or running jobs can be cancelled'),409
        c.execute("UPDATE jobs SET status='cancelled',finished_at=? WHERE id=?",(now(),job_id)); log(c,job_id,'Job cancelled by user')
    return jsonify(ok=True)

@app.post('/api/jobs/<int:job_id>/retry')
@login_required
@csrf_protect
def retry_job(job_id):
    with lock,conn() as c:
        j=c.execute('SELECT * FROM jobs WHERE id=? AND user_id=?',(job_id,session['user_id'])).fetchone()
        if not j: abort(404)
        if j['status'] not in ('failed','completed','cancelled'): return jsonify(error='Only finished jobs can be re-run'),409
        cur=c.execute('INSERT INTO jobs(user_id,name,type,status,priority,cpu,ram,gpu,command,created_at,retry_count,auto_retry,max_retries) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',(session['user_id'],j['name']+' (re-run)',j['type'],'pending',j['priority'],j['cpu'],j['ram'],j['gpu'],j['command'],now(),j['retry_count']+1,j['auto_retry'],j['max_retries']))
        log(c,cur.lastrowid,f'Cloned from job #{job_id}'); new=row(c.execute('SELECT * FROM jobs WHERE id=?',(cur.lastrowid,)).fetchone())
    return jsonify(new),201

@app.get('/api/notifications')
@login_required
def notifications():
    with conn() as c: items=[row(r) for r in c.execute('SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 30',(session['user_id'],))]
    return jsonify(items=items,unread=sum(not n['read'] for n in items))

@app.post('/api/notifications/read')
@login_required
@csrf_protect
def notifications_read():
    with conn() as c: c.execute('UPDATE notifications SET read=1 WHERE user_id=?',(session['user_id'],))
    return jsonify(ok=True)

@app.get('/api/workers')
@login_required
def workers():
    with conn() as c:
        usage=worker_usage(c); out=[]
        for w in c.execute('SELECT * FROM workers'):
            u=usage.get(w['id'],(0,0,0)); n=c.execute("SELECT COUNT(*) FROM jobs WHERE status='running' AND worker_id=?",(w['id'],)).fetchone()[0]
            out.append(dict(id=w['id'],name=w['name'],running_jobs=n,cpu_total=w['cpu_total'],cpu_used=u[0],ram_total=w['ram_total'],ram_used=u[1],gpu_total=w['gpu_total'],gpu_used=u[2],status='busy' if n else 'idle'))
    return jsonify(out)

@app.get('/api/stats')
@login_required
def stats():
    uid=session['user_id']
    with conn() as c:
        by_status={r['status']:r['n'] for r in c.execute('SELECT status,COUNT(*) n FROM jobs WHERE user_id=? GROUP BY status',(uid,))}; by_type={r['type']:r['n'] for r in c.execute('SELECT type,COUNT(*) n FROM jobs WHERE user_id=? GROUP BY type',(uid,))}
        durations=[(datetime.fromisoformat(r['finished_at'])-datetime.fromisoformat(r['started_at'])).total_seconds() for r in c.execute("SELECT started_at,finished_at FROM jobs WHERE user_id=? AND status='completed' AND started_at IS NOT NULL AND finished_at IS NOT NULL",(uid,))]
        samples=[row(r) for r in c.execute('SELECT ts,cpu,ram,gpu FROM samples ORDER BY rowid DESC LIMIT 40')][::-1]
    done,failed=by_status.get('completed',0),by_status.get('failed',0)
    return jsonify(by_status=by_status,by_type=by_type,total=sum(by_status.values()),success_rate=round(100*done/(done+failed),1) if done+failed else None,avg_duration=round(sum(durations)/len(durations),1) if durations else None,utilization=samples)


# --------------------------- CloudFlow Intelligence Lab ---------------------------
def _resource_payload(d):
    try:
        cpu, ram, gpu = int(d.get('cpu', 4)), int(d.get('ram', 8)), int(d.get('gpu', 0))
    except (TypeError, ValueError):
        raise ValueError('CPU, RAM and GPU must be whole numbers')
    if not (1 <= cpu <= 64 and 1 <= ram <= 256 and 0 <= gpu <= 4):
        raise ValueError('Resources out of range (CPU 1-64, RAM 1-256 GB, GPU 0-4)')
    return cpu, ram, gpu

@app.post('/api/optimizer/recommend')
@login_required
@csrf_protect
def optimizer_recommend():
    d=request.get_json(silent=True) or {}
    try: cpu,ram,gpu=_resource_payload(d)
    except ValueError as e: return jsonify(error=str(e)),400
    typ=d.get('type','Custom')
    # Transparent rule-based sizing: recommendations are estimates, not learned predictions.
    factors={'Model Training':(.65,.70,1 if gpu else 0),'Data Processing':(.55,.60,0),'Image Analysis':(.60,.65,1 if gpu else 0),'Simulation':(.70,.70,0),'Batch Inference':(.50,.55,1 if gpu else 0),'Custom':(.75,.75,gpu)}
    cf,rf,gf=factors.get(typ,factors['Custom'])
    rec_cpu=max(1,min(cpu,round(cpu*cf))); rec_ram=max(1,min(ram,round(ram*rf))); rec_gpu=min(gpu,gf)
    with conn() as c:
        workers=c.execute('SELECT * FROM workers').fetchall()
        fitting=[w for w in workers if rec_cpu<=w['cpu_total'] and rec_ram<=w['ram_total'] and rec_gpu<=w['gpu_total']]
    return jsonify(recommended={'cpu':rec_cpu,'ram':rec_ram,'gpu':rec_gpu},requested={'cpu':cpu,'ram':ram,'gpu':gpu},fits_worker=bool(fitting),worker_options=[w['name'] for w in fitting],explanation='Rule-based estimate using the selected job type. Validate with a small run; it is not an ML-trained optimizer.')

@app.post('/api/prediction/risk')
@login_required
@csrf_protect
def prediction_risk():
    d=request.get_json(silent=True) or {}
    try: cpu,ram,gpu=_resource_payload(d)
    except ValueError as e: return jsonify(error=str(e)),400
    typ=d.get('type','Custom'); reasons=[]; score=8
    with conn() as c:
        workers=c.execute('SELECT * FROM workers').fetchall()
        if not any(cpu<=w['cpu_total'] and ram<=w['ram_total'] and gpu<=w['gpu_total'] for w in workers): score+=60; reasons.append('No worker has enough total capacity')
        usage=worker_usage(c)
        max_pressure=0
        for w in workers:
            u=usage.get(w['id'],(0,0,0))
            pressure=max(u[0]/w['cpu_total'],u[1]/w['ram_total'],u[2]/w['gpu_total'] if w['gpu_total'] else 0)
            max_pressure=max(max_pressure,pressure)
        if max_pressure>.75: score+=22; reasons.append('Current worker utilization is high')
        history=c.execute("SELECT COUNT(*) total,SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) failed FROM jobs WHERE user_id=? AND type=?",(session['user_id'],typ)).fetchone()
        if history['total']>=3 and history['failed']/history['total']>.25: score+=20; reasons.append('Your recent jobs of this type have an elevated failure rate')
    score=min(95,score); band='low' if score<30 else 'medium' if score<60 else 'high'
    if not reasons: reasons=['No major risk signals found in current capacity and your job history']
    return jsonify(score=score,band=band,reasons=reasons,method='Transparent rule-based heuristic; not a trained machine-learning model.')

@app.post('/api/simulate/whatif')
@login_required
@csrf_protect
def whatif_simulation():
    d=request.get_json(silent=True) or {}
    try: extra=int(d.get('extra_workers',1)); cpu=int(d.get('cpu',32)); ram=int(d.get('ram',128)); gpu=int(d.get('gpu',1))
    except (TypeError,ValueError): return jsonify(error='Worker capacity values must be whole numbers'),400
    if not (0<=extra<=10 and 1<=cpu<=256 and 1<=ram<=1024 and 0<=gpu<=16): return jsonify(error='Use 0–10 workers, 1–256 CPU, 1–1024 GB RAM and 0–16 GPUs'),400
    with conn() as c:
        workers=c.execute('SELECT * FROM workers').fetchall(); jobs=c.execute("SELECT * FROM jobs WHERE user_id=? AND status='pending' ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END,id",(session['user_id'],)).fetchall()
        current=sum(w['cpu_total'] for w in workers); extra_capacity=extra*cpu
        fit_now=sum(1 for j in jobs if any(j['cpu']<=w['cpu_total'] and j['ram']<=w['ram_total'] and j['gpu']<=w['gpu_total'] for w in workers))
        fit_after=sum(1 for j in jobs if any(j['cpu']<=w['cpu_total'] and j['ram']<=w['ram_total'] and j['gpu']<=w['gpu_total'] for w in workers) or (extra>0 and j['cpu']<=cpu and j['ram']<=ram and j['gpu']<=gpu))
    return jsonify(pending_jobs=len(jobs),currently_fit=fit_now,fit_with_extra_workers=fit_after,additional_jobs_supported=max(0,fit_after-fit_now),cpu_capacity_now=current,cpu_capacity_after=current+extra_capacity,assumptions=f'Simulated {extra} identical worker(s), each with {cpu} CPU, {ram} GB RAM and {gpu} GPU. This is a capacity scenario, not a live deployment.')

@app.post('/api/carbon/estimate')
@login_required
@csrf_protect
def carbon_estimate():
    d=request.get_json(silent=True) or {}
    try: cpu,ram,gpu=_resource_payload(d); hours=float(d.get('runtime_hours',1)); intensity=float(d.get('grid_intensity',400)); future_intensity=float(d.get('future_grid_intensity',intensity))
    except (TypeError,ValueError): return jsonify(error='Enter valid resource values, runtime and grid intensity'),400
    if not (0.01<=hours<=10000 and 10<=intensity<=1200 and 10<=future_intensity<=1200): return jsonify(error='Runtime must be 0.01–10000 hours and grid intensities 10–1200 gCO2/kWh'),400
    # Illustrative power model, intentionally disclosed to the user.
    power_kw=cpu*.045+ram*.002+gpu*.22; energy_kwh=power_kw*hours; grams=energy_kwh*intensity
    future_grams=energy_kwh*future_intensity
    return jsonify(estimated_power_kw=round(power_kw,3),energy_kwh=round(energy_kwh,3),carbon_grams=round(grams,1),carbon_kg=round(grams/1000,4),grid_intensity=intensity,future_grid_intensity=future_intensity,future_carbon_grams=round(future_grams,1),estimated_saving_grams=round(max(0,grams-future_grams),1),green_window_recommended=future_intensity<intensity,assumptions='Illustrative estimate: 45 W per CPU core, 2 W per GB RAM, 220 W per GPU. Default grid intensity is 400 gCO2/kWh; replace it with a verified regional value for reporting.')

@app.post('/api/assistant')
@login_required
@csrf_protect
def assistant_query():
    d=request.get_json(silent=True) or {}; prompt=str(d.get('prompt','')).strip()[:500]
    if not prompt: return jsonify(error='Enter a question'),400
    q=prompt.lower(); uid=session['user_id']
    with conn() as c:
        if 'failed' in q:
            items=[row(x) for x in c.execute("SELECT id,name,status FROM jobs WHERE user_id=? AND status='failed' ORDER BY id DESC LIMIT 10",(uid,))]
            answer=f'You have {len(items)} failed job(s) in the latest 10 results.'
        elif 'cancel' in q:
            items=[row(x) for x in c.execute("SELECT id,name,status FROM jobs WHERE user_id=? AND status IN ('pending','running') ORDER BY id DESC LIMIT 10",(uid,))]
            answer='These are your active jobs. Open a job to cancel it; the assistant will not cancel jobs without your confirmation.'
        elif 'worker' in q:
            items=[row(x) for x in c.execute('SELECT id,name,cpu_total,ram_total,gpu_total FROM workers ORDER BY id')]
            answer=f'There are {len(items)} configured workers. See their live utilization on the Workers page.'
        elif 'pending' in q or 'queue' in q:
            items=[row(x) for x in c.execute("SELECT id,name,status FROM jobs WHERE user_id=? AND status='pending' ORDER BY id DESC LIMIT 10",(uid,))]
            answer=f'You have {len(items)} pending job(s) in the latest 10 results.'
        else:
            items=[row(x) for x in c.execute('SELECT id,name,status FROM jobs WHERE user_id=? ORDER BY id DESC LIMIT 5',(uid,))]
            answer='I can summarize your failed jobs, pending queue, active jobs to cancel, or configured workers. Try asking one of those questions.'
    return jsonify(answer=answer,items=items,notice='CloudFlow Assistant uses local intent rules; it does not call an external AI service.')

@app.post('/api/workflows')
@login_required
@csrf_protect
def create_workflow():
    d=request.get_json(silent=True) or {}; name=str(d.get('name','')).strip()[:80]; steps=d.get('steps')
    if not name: return jsonify(error='Workflow name is required'),400
    if not isinstance(steps,list) or not 2<=len(steps)<=8: return jsonify(error='Provide between 2 and 8 workflow steps'),400
    normalized=[]
    for i,step in enumerate(steps):
        try: cpu,ram,gpu=_resource_payload(step)
        except ValueError as e: return jsonify(error=f'Step {i+1}: {e}'),400
        typ=step.get('type','Custom')
        if typ not in JOB_TYPES: return jsonify(error=f'Step {i+1}: unknown job type'),400
        normalized.append((str(step.get('name') or f'Step {i+1}')[:80],typ,cpu,ram,gpu))
    import uuid
    wid=uuid.uuid4().hex[:12]
    with lock,conn() as c:
        workers=c.execute('SELECT * FROM workers').fetchall()
        if any(not any(x[2]<=w['cpu_total'] and x[3]<=w['ram_total'] and x[4]<=w['gpu_total'] for w in workers) for x in normalized): return jsonify(error='At least one workflow step cannot fit on any configured worker'),400
        c.execute('INSERT INTO workflows(id,user_id,name,created_at) VALUES (?,?,?,?)',(wid,session['user_id'],name,now()))
        previous=None; ids=[]
        for i,(step_name,typ,cpu,ram,gpu) in enumerate(normalized):
            cur=c.execute('INSERT INTO jobs(user_id,name,type,status,priority,cpu,ram,gpu,created_at,workflow_id,step_order,depends_on_job_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(session['user_id'],step_name,typ,'pending','normal',cpu,ram,gpu,now(),wid,i,previous))
            jid=cur.lastrowid; ids.append(jid); log(c,jid,f'Workflow {name}: step {i+1} of {len(normalized)} queued'); previous=jid
    return jsonify(id=wid,name=name,job_ids=ids),201

@app.get('/api/workflows')
@login_required
def list_workflows():
    with conn() as c:
        rows=c.execute('SELECT * FROM workflows WHERE user_id=? ORDER BY created_at DESC',(session['user_id'],)).fetchall(); out=[]
        for w in rows:
            steps=[row(x) for x in c.execute('SELECT id,name,status,progress,step_order,depends_on_job_id FROM jobs WHERE workflow_id=? AND user_id=? ORDER BY step_order',(w['id'],session['user_id']))]
            out.append(dict(id=w['id'],name=w['name'],created_at=w['created_at'],steps=steps))
    return jsonify(items=out)

if __name__=='__main__':
    init_db(); start_scheduler(); port=int(os.environ.get('PORT','5000')); app.run(host=os.environ.get('HOST','127.0.0.1'),port=port,debug=False,threaded=True)
