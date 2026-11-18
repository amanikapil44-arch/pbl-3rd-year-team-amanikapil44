import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest

@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / 'test.db'
    monkeypatch.setenv('CLOUDFLOW_DB', str(db))
    import app as cloud
    cloud.DB = str(db)
    cloud.init_db()
    cloud.app.config.update(TESTING=True, SECRET_KEY='test-secret')
    with cloud.app.test_client() as client:
        yield client

def register(client):
    r=client.post('/api/auth/register',json={'username':'tester','password':'long-password-123'})
    assert r.status_code==201
    return r.get_json()['csrf_token']

def test_register_and_private_job_listing(client):
    token=register(client)
    r=client.post('/api/jobs',json={'name':'private job','cpu':2,'ram':4,'gpu':0},headers={'X-CSRF-Token':token})
    assert r.status_code==201
    result=client.get('/api/jobs').get_json()
    assert result['total']==1 and result['items'][0]['name']=='private job'

def test_reject_impossible_worker_request(client):
    token=register(client)
    r=client.post('/api/jobs',json={'name':'too big','cpu':64,'ram':256,'gpu':4},headers={'X-CSRF-Token':token})
    assert r.status_code==400

def test_cancel_conflict_and_rerun(client):
    token=register(client)
    created=client.post('/api/jobs',json={'name':'sample','cpu':1,'ram':1,'gpu':0},headers={'X-CSRF-Token':token}).get_json()
    assert client.post(f"/api/jobs/{created['id']}/cancel",headers={'X-CSRF-Token':token}).status_code==200
    assert client.post(f"/api/jobs/{created['id']}/cancel",headers={'X-CSRF-Token':token}).status_code==409
    assert client.post(f"/api/jobs/{created['id']}/retry",headers={'X-CSRF-Token':token}).status_code==201

def test_auth_required(client):
    assert client.get('/api/jobs').status_code==401

def test_optimizer_prediction_whatif_carbon_and_assistant(client):
    token=register(client)
    headers={'X-CSRF-Token':token}
    payload={'type':'Model Training','cpu':8,'ram':16,'gpu':1}
    opt=client.post('/api/optimizer/recommend',json=payload,headers=headers)
    assert opt.status_code==200 and opt.get_json()['recommended']['cpu'] <= 8
    risk=client.post('/api/prediction/risk',json=payload,headers=headers)
    assert risk.status_code==200 and 0 <= risk.get_json()['score'] <= 100
    sim=client.post('/api/simulate/whatif',json={'extra_workers':2,'cpu':32,'ram':128,'gpu':2},headers=headers)
    assert sim.status_code==200 and sim.get_json()['cpu_capacity_after'] > sim.get_json()['cpu_capacity_now']
    carbon=client.post('/api/carbon/estimate',json={**payload,'runtime_hours':2,'grid_intensity':400},headers=headers)
    assert carbon.status_code==200 and carbon.get_json()['carbon_grams'] > 0
    assistant=client.post('/api/assistant',json={'prompt':'show my failed jobs'},headers=headers)
    assert assistant.status_code==200 and 'failed' in assistant.get_json()['answer'].lower()

def test_workflow_creates_sequential_dependencies(client):
    token=register(client); headers={'X-CSRF-Token':token}
    r=client.post('/api/workflows',json={'name':'demo pipeline','steps':[
        {'name':'prepare','type':'Data Processing','cpu':2,'ram':4,'gpu':0},
        {'name':'train','type':'Model Training','cpu':8,'ram':16,'gpu':1},
        {'name':'evaluate','type':'Batch Inference','cpu':2,'ram':4,'gpu':0}
    ]},headers=headers)
    assert r.status_code==201
    ids=r.get_json()['job_ids']
    import app as cloud
    with cloud.conn() as c:
        rows=c.execute('SELECT id,depends_on_job_id FROM jobs WHERE id IN (?,?,?) ORDER BY step_order',ids).fetchall()
        assert rows[0]['depends_on_job_id'] is None
        assert rows[1]['depends_on_job_id']==ids[0]
        assert rows[2]['depends_on_job_id']==ids[1]
    assert len(client.get('/api/workflows').get_json()['items'])==1

def test_auto_retry_requeues_failed_simulated_attempt(client, monkeypatch):
    token=register(client); headers={'X-CSRF-Token':token}
    job=client.post('/api/jobs',json={'name':'recover me','cpu':1,'ram':1,'gpu':0,'auto_retry':True,'max_retries':2},headers=headers).get_json()
    import app as cloud
    with cloud.conn() as c:
        c.execute("UPDATE jobs SET status='running',progress=99,auto_retry=1,max_retries=2 WHERE id=?",(job['id'],))
    monkeypatch.setattr(cloud.random,'random',lambda:0.0)
    monkeypatch.setattr(cloud.random,'randint',lambda a,b:5)
    cloud.tick()
    with cloud.conn() as c:
        result=c.execute('SELECT status,retry_count,progress FROM jobs WHERE id=?',(job['id'],)).fetchone()
    assert result['status']=='pending' and result['retry_count']==1 and result['progress']==0
