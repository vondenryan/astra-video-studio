from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from unittest.mock import Mock

import pytest

from astra_video_studio.ae_bridge.result_artifacts import (PROTOCOL, ACK_MAX_BYTES, EVIDENCE_MAX_BYTES,
    EVIDENCE_FILE, load_artifact, parse_json, revision_evidence_estimate)
from astra_video_studio.ae_bridge.runner import BridgeRunner
from astra_video_studio.config import Settings
from astra_video_studio.jobs import write_json
from astra_video_studio.schemas import ComponentStatus
from astra_video_studio.revisions import check_evidence_budget

ID = '1' * 32


def publish(directory, operation_id=ID, data=None, status='succeeded', bom=False):
    result = {'operation_id': operation_id, 'status': status, 'data': data or {}, 'error': 'native failure' if status == 'failed' else None}
    envelope = {'schema_version': 1, 'protocol': PROTOCOL, 'result': result}
    raw = (b'\xef\xbb\xbf' if bom else b'') + json.dumps(envelope, ensure_ascii=False).encode('utf-8')
    (directory / EVIDENCE_FILE).write_bytes(raw)
    ack = {'operation_id': operation_id, 'status': status, 'protocol': PROTOCOL, 'evidence': {'file': EVIDENCE_FILE, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}}
    return ack, result


@pytest.fixture
def owned_job(tmp_path):
    directory = tmp_path / 'jobs' / ID; directory.mkdir(parents=True)
    return Settings(tmp_path, ae_result_transport=PROTOCOL), directory


@pytest.mark.parametrize('bom', [False, True])
@pytest.mark.parametrize('status', ['succeeded', 'failed'])
def test_exact_file_bytes_unicode_and_full_failure(owned_job, bom, status):
    settings, directory = owned_job
    ack, result = publish(directory, data={'text': 'Ação 😀\n日本語', 'keys': list(range(100))}, status=status, bom=bom)
    loaded, evidence = load_artifact(settings, directory, ID, ack)
    assert loaded == result
    assert evidence['bytes'] == (directory / EVIDENCE_FILE).stat().st_size
    assert evidence['sha256'] == ack['evidence']['sha256']


@pytest.mark.parametrize('change', ['identity', 'protocol', 'status', 'filename', 'absolute', 'extra', 'hash', 'size_bool', 'size_float', 'size_large', 'size_small', 'publication'])
def test_invalid_ack_or_descriptor_refused(owned_job, change):
    settings, directory = owned_job; ack, _ = publish(directory)
    if change == 'identity': ack['operation_id'] = '2'*32
    if change == 'protocol': ack['protocol'] = 'unknown'
    if change == 'status': ack['status'] = 'running'
    if change == 'filename': ack['evidence']['file'] = '../outside.json'
    if change == 'absolute': ack['evidence']['file'] = str(directory / EVIDENCE_FILE)
    if change == 'extra': ack['evidence']['source_path'] = 'anywhere'
    if change == 'hash': ack['evidence']['sha256'] = '0'*64
    if change == 'size_bool': ack['evidence']['bytes'] = True
    if change == 'size_float': ack['evidence']['bytes'] = 100.0
    if change == 'size_large': ack['evidence']['bytes'] = EVIDENCE_MAX_BYTES + 1
    if change == 'size_small': ack['evidence']['bytes'] -= 1
    if change == 'publication': ack['publication_error'] = 'disk full'
    with pytest.raises(ValueError): load_artifact(settings, directory, ID, ack)


@pytest.mark.parametrize('change', ['operation', 'status', 'schema_bool', 'protocol', 'data', 'diagnostic', 'truncated', 'duplicate', 'nonfinite'])
def test_hash_correct_but_invalid_complete_result_refused(owned_job, change):
    settings, directory = owned_job; ack, _ = publish(directory)
    path = directory / EVIDENCE_FILE; value = json.loads(path.read_text())
    if change == 'operation': value['result']['operation_id'] = '2'*32
    if change == 'status': value['result']['status'] = 'failed'; value['result']['error'] = 'changed'
    if change == 'schema_bool': value['schema_version'] = True
    if change == 'protocol': value['protocol'] = 'unknown'
    if change == 'data': value['result']['data'] = []
    if change == 'diagnostic': value['result']['status'] = 'failed'; ack['status'] = 'failed'
    raw = json.dumps(value).encode()
    if change == 'truncated': raw = raw[:20]
    if change == 'duplicate': raw = raw.replace(b'"schema_version": 1', b'"schema_version": 1, "schema_version": 1')
    if change == 'nonfinite': raw = raw.replace(b'"data": {}', b'"data": {"x": NaN}')
    path.write_bytes(raw)
    ack['evidence'].update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    with pytest.raises(ValueError): load_artifact(settings, directory, ID, ack)


@pytest.fixture
def fake_transport(monkeypatch):
    monkeypatch.setattr('astra_video_studio.ae_bridge.runner.AELock', lambda: nullcontext())
    monkeypatch.setattr('astra_video_studio.ae_bridge.runner.discover_ae', lambda _: ComponentStatus(available=True, path='AfterFX.exe'))
    monkeypatch.setattr('astra_video_studio.ae_bridge.runner.IdleTransport.ensure_ready', lambda *args: {'instance_id': 'fixture', 'transport': 'idle_inbox'})


def test_large_evidence_small_ack_and_complete_internal_result(tmp_path, fake_transport, monkeypatch):
    settings = Settings(tmp_path, ae_result_transport=PROTOCOL)
    data = {'text': 'ç' * 1_100_000, 'unchanged_sentinel': {'color': [1, 0.5, 0]}}
    def reply(self, job):
        ack, _ = publish(job.directory, job.id, data, bom=True)
        assert ack['evidence']['bytes'] > 2_000_000
        write_json(job.directory/'result.json', ack)
    monkeypatch.setattr('astra_video_studio.ae_bridge.runner.IdleTransport.publish', reply)
    result = BridgeRunner(settings).run('inspect', {})
    assert result.status == 'succeeded' and result.data == data
    directory = tmp_path/'jobs'/result.operation_id
    assert (directory/'result.json').stat().st_size < ACK_MAX_BYTES
    assert not (tmp_path/'ae-pending.json').exists()
    journal = json.loads((directory/'job.json').read_text())
    assert journal['native_evidence']['bytes'] > 2_000_000
    assert journal['result']['data'] == data


@pytest.mark.parametrize('failure', ['corrupt', 'missing', 'downgrade', 'oversize_ack', 'publication'])
def test_invalid_evidence_keeps_pending_and_blocks_next(tmp_path, fake_transport, monkeypatch, failure):
    settings = Settings(tmp_path, ae_result_transport=PROTOCOL)
    def reply(self, job):
        ack, result = publish(job.directory, job.id, {'data': 'complete'})
        if failure == 'corrupt': (job.directory/EVIDENCE_FILE).write_text('changed')
        if failure == 'missing': (job.directory/EVIDENCE_FILE).unlink()
        if failure == 'downgrade': ack = result
        if failure == 'oversize_ack': ack['padding'] = 'x'*ACK_MAX_BYTES
        if failure == 'publication': ack['publication_error'] = 'disk full'
        write_json(job.directory/'result.json', ack)
    mocked = Mock(side_effect=reply)
    monkeypatch.setattr('astra_video_studio.ae_bridge.runner.IdleTransport.publish', lambda self, job: mocked(self, job))
    result = BridgeRunner(settings, timeout=0.15).run('inspect', {})
    assert result.status == 'timeout' and 'quarantined' in result.error
    pending = tmp_path/'ae-pending.json'; before = pending.read_bytes()
    second = BridgeRunner(settings, timeout=0.15).run('inspect', {})
    assert second.status == 'blocked' and mocked.call_count == 1
    assert pending.read_bytes() == before


def test_valid_native_failure_is_acknowledged_not_retried(tmp_path, fake_transport, monkeypatch):
    settings = Settings(tmp_path, ae_result_transport=PROTOCOL)
    def reply(self, job):
        ack, _ = publish(job.directory, job.id, {'diagnostics': 'full retained evidence'}, status='failed')
        write_json(job.directory/'result.json', ack)
    monkeypatch.setattr('astra_video_studio.ae_bridge.runner.IdleTransport.publish', reply)
    result = BridgeRunner(settings).run('inspect', {})
    assert result.status == 'failed' and result.error == 'native failure'
    assert result.data['diagnostics'] == 'full retained evidence'
    assert not (tmp_path/'ae-pending.json').exists()


def test_revision_budget_uses_explicit_channel_and_generated_key_growth(tmp_path):
    state = {'large': 'x'*500_000}
    inline = Settings(tmp_path, ae_result_transport='inline-v1')
    artifact = Settings(tmp_path, ae_result_transport=PROTOCOL)
    with pytest.raises(ValueError): check_evidence_budget(inline, state, [{}, {}])
    assert check_evidence_budget(artifact, state, [{}, {}])['limit_bytes'] == EVIDENCE_MAX_BYTES
    estimate = revision_evidence_estimate(state, [{'tracks': 'x'*600_000}, {}])
    assert estimate > revision_evidence_estimate(state, [{}, {}])
    with pytest.raises(ValueError): check_evidence_budget(artifact, {'large': 'x'*EVIDENCE_MAX_BYTES}, [{}])


def test_configuration_requires_known_protocol(tmp_path, monkeypatch):
    monkeypatch.delenv('ASTRA_AE_RESULT_TRANSPORT', raising=False)
    assert Settings.from_env().ae_result_transport == PROTOCOL
    monkeypatch.setenv('ASTRA_AE_RESULT_TRANSPORT', 'artifact-v1')
    assert Settings.from_env().ae_result_transport == PROTOCOL
    with pytest.raises(ValueError): Settings(tmp_path, ae_result_transport='arbitrary-path')


@pytest.mark.parametrize('data', [b'', b'abc', b'\xef\xbb\xbf'+ 'Ação 😀\n日本語'.encode(), bytes(range(256))*257, b'x'*1_000_000] + [b'x'*n for n in (55,56,63,64,65,127,128,129)])
def test_native_es3_sha256_against_python_vectors(tmp_path, data):
    node = shutil.which('node')
    if not node: pytest.skip('Optional Node harness; actual AE acceptance separately checks the native file hash')
    source = Path('src/astra_video_studio/ae_bridge/scripts/project.jsx').read_text(encoding='utf-8')
    function = source[source.index('    function nativeResultHash('):source.index('    function publishNativeResult(')]
    fixture = tmp_path/'binary-fixture'; fixture.write_bytes(data)
    script = tmp_path/'sha-test.cjs'
    script.write_text("const fs=require('fs');\n" + function + "\nconst b=fs.readFileSync(process.argv[2]); let pos=0; const file={length:b.length,open:()=>true,close:()=>{},get eof(){return pos>=b.length},read(n){let s=b.subarray(pos,pos+n).toString('latin1');pos+=s.length;return s;}};process.stdout.write(nativeResultHash(file));", encoding='utf-8')
    tested = subprocess.run([node, str(script), str(fixture)], capture_output=True, text=True, timeout=30)
    assert tested.returncode == 0, tested.stderr
    assert tested.stdout == hashlib.sha256(data).hexdigest()
