import json, os, tempfile, threading, time, urllib.request, urllib.error
from pathlib import Path
from ac.config import ACConfig
from ac.kernel import Kernel
from ac.server import create_sidecar_server

passed=[]
def check(name, fn):
    fn(); passed.append(name); print('PASS', name)

def test_scope_isolation():
    with tempfile.TemporaryDirectory() as td:
        k=Kernel(ACConfig(data_dir=td))
        k.remember_scoped('user-A','secret from A', tags=['private'])
        a=k.recall_scoped('user-A','secret A')
        b=k.recall_scoped('user-B','secret A')
        assert any('secret from A' in x['content'] for x in a)
        assert not any('secret from A' in x['content'] for x in b)
        assert 'user-A' not in str(list((Path(td)/'private').rglob('*')))

def test_private_stimulus_workspace():
    with tempfile.TemporaryDirectory() as td:
        k=Kernel(ACConfig(data_dir=td))
        msg='VERY_PRIVATE_MARKER_78392'
        k.tick(stimulus=msg, source='private_user', memory_scope='user-A', persist_stimulus=False)
        snapshot=json.dumps(k.status(), ensure_ascii=False)
        assert msg not in snapshot
        assert msg not in (Path(td)/'eternal_chain.jsonl').read_text()
        assert not any(msg in f.read_text(errors='ignore') for f in (Path(td)/'private').rglob('*.jsonl'))

def test_heartbeat_lifecycle():
    with tempfile.TemporaryDirectory() as td:
        k=Kernel(ACConfig(data_dir=td, tick_interval_sec=0.25))
        s=k.start_heartbeat()
        assert s['running']
        time.sleep(0.9)
        stopped=k.stop_heartbeat()
        assert stopped['ticks'] >= 2
        assert not stopped['running']
        assert not k.heartbeat_status()['running']

def test_api_perceive_commit():
    with tempfile.TemporaryDirectory() as td:
        cfg=ACConfig(data_dir=td, server_host='127.0.0.1', server_port=0)
        k=Kernel(cfg)
        server=create_sidecar_server(k)
        thread=threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            host,port=server.server_address
            base=f'http://{host}:{port}'
            req=urllib.request.Request(base+'/v1/perceive', data=json.dumps({
                'sender_id':'628123@s.whatsapp.net',
                'message':'Aku sedang mengembangkan NADI',
                'private_memory_context':[{'content':'Pengguna sedang membangun bot WhatsApp.'}],
            }).encode(), headers={'Content-Type':'application/json'}, method='POST')
            with urllib.request.urlopen(req, timeout=5) as res:
                data=json.loads(res.read())
            assert data['status']=='ok'
            assert 'Pengguna sedang membangun bot WhatsApp' in data['system_context']
            assert data['privacy']['raw_message_persisted_by_nadi'] is False
            reply='private assistant reply must not be stored raw'
            req=urllib.request.Request(base+'/v1/commit', data=json.dumps({
                'sender_id':'628123@s.whatsapp.net','content':reply,
            }).encode(), headers={'Content-Type':'application/json'}, method='POST')
            with urllib.request.urlopen(req, timeout=5) as res:
                committed=json.loads(res.read())
            assert committed['raw_content_stored'] is False
            private_files=list((Path(td)/'private').rglob('*.jsonl'))
            assert private_files
            assert all(reply not in f.read_text(errors='ignore') for f in private_files)
        finally:
            server.shutdown(); thread.join(timeout=5); server.server_close()
            assert not k.heartbeat_status()['running']

def test_non_loopback_requires_token():
    with tempfile.TemporaryDirectory() as td:
        k=Kernel(ACConfig(data_dir=td))
        old=os.environ.pop('NADI_API_TOKEN', None)
        try:
            try:
                create_sidecar_server(k, host='0.0.0.0', port=0)
            except RuntimeError:
                return
            raise AssertionError('expected remote bind to be refused')
        finally:
            if old is not None: os.environ['NADI_API_TOKEN']=old

for name,fn in [
 ('private scope isolation',test_scope_isolation),
 ('private stimulus never enters global NADI state',test_private_stimulus_workspace),
 ('managed heartbeat start/stop',test_heartbeat_lifecycle),
 ('secure sidecar perceive/commit lifecycle',test_api_perceive_commit),
 ('remote binding requires bearer token',test_non_loopback_requires_token),
]: check(name,fn)
print(f'{len(passed)}/5 tests passed')

def test_exclusive_process_lock():
    with tempfile.TemporaryDirectory() as td:
        k1=Kernel(ACConfig(data_dir=td))
        try:
            try:
                Kernel(ACConfig(data_dir=td))
            except RuntimeError as exc:
                assert 'Another NADI process' in str(exc)
            else:
                raise AssertionError('second writer was not blocked')
        finally:
            k1.close()
        k2=Kernel(ACConfig(data_dir=td)); k2.close()

def test_corrupt_snapshot_quarantine():
    with tempfile.TemporaryDirectory() as td:
        k=Kernel(ACConfig(data_dir=td)); k.close()
        snap=Path(td)/'kernel_state.json'
        snap.write_text('{broken', encoding='utf-8')
        try:
            Kernel(ACConfig(data_dir=td))
        except RuntimeError as exc:
            assert 'corrupt' in str(exc).lower()
        else:
            raise AssertionError('corrupt snapshot should not be silently reset')
        assert list(Path(td).glob('kernel_state.corrupt.*.json'))

def test_one_hour_1hz_homeostatic_stability():
    # Regression guard for Ocha's real 1 Hz operational heartbeat calibration.
    from ac.intero import Interoception
    with tempfile.TemporaryDirectory() as td:
        cfg = ACConfig(data_dir=td, energy_setpoint=0.80, thermal_setpoint=0.25)
        state = Interoception()
        for _ in range(3600):
            state.update(cfg, dt=1.0, cognitive_effort=0.15)
        assert 0.75 <= state.energy <= 0.90, state.to_dict()
        assert 0.15 <= state.thermal_load <= 0.35, state.to_dict()
        assert 0.0 <= state.allostatic_load <= 1.0, state.to_dict()
        assert state.energy < 1.0 and state.thermal_load < 1.0

def test_remote_token_auth():
    with tempfile.TemporaryDirectory() as td:
        k=Kernel(ACConfig(data_dir=td))
        old=os.environ.get('NADI_API_TOKEN')
        os.environ['NADI_API_TOKEN']='test-token-very-long-random-123456789'
        server=create_sidecar_server(k, host='0.0.0.0', port=0)
        thread=threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            port=server.server_address[1]
            url=f'http://127.0.0.1:{port}/v1/health'
            try:
                urllib.request.urlopen(url, timeout=3)
            except urllib.error.HTTPError as e:
                assert e.code==401
            else:
                raise AssertionError('missing bearer token was accepted')
            req=urllib.request.Request(url, headers={'Authorization':'Bearer test-token-very-long-random-123456789'})
            with urllib.request.urlopen(req, timeout=3) as res:
                assert json.loads(res.read())['service_version']=='2.1.0'
        finally:
            server.shutdown(); thread.join(timeout=3); server.server_close()
            if old is None: os.environ.pop('NADI_API_TOKEN',None)
            else: os.environ['NADI_API_TOKEN']=old

for name,fn in [
 ('exclusive process lock',test_exclusive_process_lock),
 ('corrupt snapshot quarantine',test_corrupt_snapshot_quarantine),
 ('remote bearer token authentication',test_remote_token_auth),
 ('one-hour 1 Hz homeostatic stability',test_one_hour_1hz_homeostatic_stability),
]: check(name,fn)
print(f'{len(passed)}/9 extended tests passed')
