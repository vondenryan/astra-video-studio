"""Opt-in real AE read-only dependency report and durable worker/cancellation acceptance."""
import asyncio
import os
from pathlib import Path
import struct
import subprocess
import sys
import time
from uuid import uuid4
import zlib

from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
import pytest

from astra_video_studio.ae_bridge.idle_transport import IdleTransport
from astra_video_studio.ae_bridge.result_artifacts import parse_json,load_artifact
from astra_video_studio.config import Settings
from astra_video_studio.existing_projects import digest
from astra_video_studio.jobs import read_json,write_json
from astra_video_studio.project_manager import ProjectManager


def png(path):
    def chunk(name,data):return struct.pack('>I',len(data))+name+data+struct.pack('>I',zlib.crc32(name+data)&0xffffffff)
    raw=b''.join(b'\0'+bytes([20,180,230])*64 for _ in range(64))
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',64,64,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b''))


@pytest.mark.ae_live
@pytest.mark.skipif(os.environ.get('ASTRA_RUN_AE_TESTS')!='1',reason='Opt-in Sprint13 native recovery acceptance')
def test_real_dependencies_missing_media_worker_and_native_cancel():
    s=Settings.from_env();state=IdleTransport(s).state()
    assert state and not state.get('active_job')
    assert not s.contained_path('ae-pending.json').exists() and not s.contained_path('preview-pending.json').exists()
    original={p:digest(Path(p)) for p in ProjectManager(s).managed_paths()}
    out=s.contained_path('sprint13-native-'+uuid4().hex);out.mkdir();png(out/'source.png')
    write_json(out/'preservation-baseline.json',{'sources':original})
    async def exercise():
        params=StdioServerParameters(command=sys.executable,args=['-m','astra_video_studio.mcp_server'],env=dict(os.environ))
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as client:
                await client.initialize()
                async def call(name,request=None,**kwargs):
                    args={'response_mode':'full',**kwargs}
                    if request is not None:args['request']=request
                    response=await client.call_tool(name,args);assert not response.isError,response.content
                    result=response.structuredContent
                    assert result['status']=='succeeded',result
                    return result
                created=await call('project_create',{'name':'Sprint13 Recovery','title':'RECOVERY','duration':3,
                    'width':640,'height':360,'fps':24,'font_size':50})
                pid=created['project_id'];cid=created['data']['compositions'][0]['composition_id'].split(':')[-1]
                imported=await call('media_import',{'project_id':pid,'source_path':str(out/'source.png')})
                source=Path(imported['project_path']);source_sha=digest(source)
                live=await call('project_dependencies',{'project_id':pid,'refresh':True})
                assert live['data']['scope']=='acknowledged_live_read' and not live['data']['issues']
                asset=s.contained_path('assets/'+imported['data']['asset_id']+'/original.png')
                asset_sha=digest(asset);held=asset.with_name('held-for-sprint13.png')
                assert not held.exists()
                asset.rename(held)
                try:
                    missing=await call('project_dependencies',{'project_id':pid})
                    assert any(i['kind']=='media' for i in missing['data']['issues'])
                finally:held.rename(asset)
                assert digest(asset)==asset_sha and digest(source)==source_sha
                async def submit():
                    response=await client.call_tool('preview_render',{'request':{'project_id':pid,'composition_id':cid,'duration':1,'max_width':640}})
                    assert not response.isError,response.content
                    queued=response.structuredContent;assert queued['status']=='queued',queued
                    return queued['job_id']
                async def wait(identifier,cancel=False):
                    deadline=time.monotonic()+240;requested=None
                    while time.monotonic()<deadline:
                        response=await client.call_tool('job_status',{'operation_id':identifier,'response_mode':'full'})
                        assert not response.isError,response.content
                        job=response.structuredContent
                        if cancel and requested is None and job.get('stage')=='aerender' and job.get('process_pid'):
                            requested={'stage':job['stage'],'pid':job['process_pid'],'identity':job.get('process_identity')}
                            reply=await client.call_tool('job_cancel',{'operation_id':identifier})
                            assert not reply.isError
                        if job['status'] not in ('prepared','queued','running'):
                            return job,requested
                        await asyncio.sleep(.1)
                    pytest.fail('Native job deadline exceeded; retain quarantine and do not retry')
                first=await submit();completed,_=await wait(first)
                assert completed['status']=='succeeded',completed
                assert read_json(s.contained_path('queue/claims/'+first+'.json'))['released']
                second=await submit();cancelled,request=await wait(second,True)
                assert request is not None,'Native cancellation phase was not observed; do not claim acceptance'
                assert cancelled['status']=='cancelled',cancelled
                assert any(e.get('process_exit_confirmed') for e in cancelled['events'])
                assert not s.contained_path('preview-pending.json').exists()
                assert digest(source)==source_sha
                checked=await call('job_reconcile',{'operation_id':second})
                queue=await call('queue_inspect',{})
                assert queue['data']['outstanding_claims']==0
                write_json(out/'acceptance.json',{'project_id':pid,'source_path':str(source),'source_sha256':source_sha,
                    'live_dependencies':live['data'],'missing_media':missing['data'],
                    'render_job_id':first,'render':completed,'cancelled_job_id':second,'cancelled':cancelled,
                    'cancel_request':request,'reconciliation':checked['data'],'queue':queue['data'],
                    'interactive_ae_terminated':False,'human_visual_review':'not performed; recovery acceptance only'})
    try:asyncio.run(exercise())
    finally:
        unchanged={p:digest(Path(p))==sha for p,sha in original.items()}
        write_json(out/'preservation-result.json',{'count':len(original),'all_preserved':all(unchanged.values())})
        assert all(unchanged.values())


@pytest.mark.ae_live
@pytest.mark.skipif(os.environ.get('ASTRA_RUN_AE_TESTS')!='1',reason='Opt-in real AE late-read host interruption')
def test_native_read_host_interruption_and_acknowledged_release():
    s=Settings.from_env();heartbeat=IdleTransport(s).state()
    assert heartbeat and not heartbeat.get('active_job')
    assert not s.contained_path('ae-pending.json').exists() and not s.contained_path('preview-pending.json').exists()
    prior=sorted((p for p in s.workspace.glob('sprint13-native-*/acceptance.json') if not p.parent.name.startswith('sprint13-native-read-recovery-')),key=lambda p:p.stat().st_mtime)
    assert prior,'Run the Sprint13 main native acceptance first'
    accepted=read_json(prior[-1]);source=Path(accepted['source_path']);source_sha=digest(source)
    baseline={p:digest(Path(p)) for p in ProjectManager(s).managed_paths()}
    out=s.contained_path('sprint13-native-read-recovery-'+uuid4().hex);out.mkdir()
    checkpoint=out/'control.json'
    fixture=str(Path('tests/fixtures/recovery_host.py').resolve())
    packages=str(Path(sys.executable).parent.parent/'Lib/site-packages')
    env=dict(os.environ,PYTHONPATH=os.pathsep.join([str(Path('src').resolve()),packages]))
    process=subprocess.Popen([sys._base_executable,fixture,'real_read',str(s.workspace),str(source),str(checkpoint)],
        env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        deadline=time.monotonic()+20;control=None
        while time.monotonic()<deadline:
            if checkpoint.is_file():
                control=read_json(checkpoint)
                assert control['pid']==process.pid,'Only the owned Python host may be interrupted'
                ack=s.contained_path(f'jobs/{control["job_id"]}/result.json')
                state=IdleTransport(s).state()
                if ack.is_file() and state and not state.get('active_job'):
                    try:
                        decoded=parse_json(ack.read_bytes())
                        load_artifact(s,ack.parent,control['job_id'],decoded)
                        if state['time_ms']>=int(ack.stat().st_mtime*1000):break
                    except (OSError,ValueError,KeyError,TypeError):pass
            time.sleep(.05)
        else:pytest.fail('No completed read ack checkpoint; retain quarantine, never resubmit')
        assert read_json(ack)['status']=='succeeded'
    finally:
        if process.poll() is None:process.kill()
        process.wait(timeout=10)
    identifier=control['job_id'];journal=s.contained_path(f'jobs/{identifier}/job.json');before=digest(journal)
    assert s.contained_path('ae-pending.json').exists()
    async def recover():
        params=StdioServerParameters(command=sys.executable,args=['-m','astra_video_studio.mcp_server'],env=dict(os.environ))
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as client:
                await client.initialize()
                async def call(tool,request):
                    response=await client.call_tool(tool,{'request':request,'response_mode':'full'})
                    assert not response.isError,response.content
                    result=response.structuredContent;assert result['status']=='succeeded',result
                    return result
                inspected=await call('job_reconcile',{'operation_id':identifier})
                assert inspected['data']['safe_release_acknowledged_read'] is True
                released=await call('job_reconcile',{'operation_id':identifier,'mode':'release_acknowledged_read','expected_journal_sha256':before})
                assert released['data']['state']=='readonly_quarantine_released'
                assert not s.contained_path('ae-pending.json').exists()
                refreshed=await call('project_dependencies',{'project_id':accepted['project_id'],'refresh':True})
                assert refreshed['data']['scope']=='acknowledged_live_read'
                write_json(out/'acceptance.json',dict(interrupted_job_id=identifier,journal_sha256=before,
                    source_path=str(source),source_sha256=source_sha,inspected=inspected['data'],released=released['data'],
                    subsequent_guarded_read=refreshed['data'],interrupted_process='owned Python host only; real AE read already acknowledged',
                    native_mutation_replayed=False,interactive_ae_terminated=False))
    asyncio.run(recover())
    assert digest(journal)==before and digest(source)==source_sha
    unchanged=all(digest(Path(p))==sha for p,sha in baseline.items())
    write_json(out/'preservation-result.json',{'count':len(baseline),'all_preserved':unchanged})
    assert unchanged
