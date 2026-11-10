"""Kill only owned fixture Python hosts; restart real MCP and never launch Adobe."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
import pytest

from astra_video_studio.existing_projects import digest
from astra_video_studio.jobs import read_json,write_json
from astra_video_studio.responses import encoded

FIXTURE=str(Path('tests/fixtures/recovery_host.py').resolve())


def wait_file(path,seconds=12):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if path.is_file():return read_json(path)
        time.sleep(.05)
    raise AssertionError('Fixture checkpoint did not arrive: '+str(path))


def host(mode,workspace):
    # Bypass Windows venv redirector so the controlled host PID is the actual
    # Python worker being interrupted, rather than its launcher.
    packages=str(Path(sys.executable).parent.parent/'Lib/site-packages')
    env=dict(os.environ,PYTHONPATH=os.pathsep.join([str(Path('src').resolve()),packages]))
    return subprocess.Popen([sys._base_executable,FIXTURE,mode,str(workspace)],env=env,stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))


async def reconcile(workspace,identifier,release=False):
    params=StdioServerParameters(command=sys.executable,args=['-m','astra_video_studio.mcp_server'],
        env=dict(os.environ,ASTRA_WORKSPACE=str(workspace)))
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as client:
            await client.initialize()
            listing=await client.list_tools();assert len(listing.tools)==77
            async def call(tool,request):
                response=await client.call_tool(tool,{'request':request})
                assert not response.isError,response.content
                assert len(encoded(response.model_dump(mode='json',exclude_none=True)))<=8192
                raw=read_json(Path(response.structuredContent['evidence']['path']))['result']
                return raw['data']
            checked=await call('job_reconcile',{'operation_id':identifier})
            page=await call('queue_inspect',{})
            assert page['capacity']==4 and not checked['automatic_retry_allowed']
            cleanup=await call('workspace_cleanup_plan',{'operation_ids':[identifier],'minimum_age_hours':24})
            assert cleanup['deletion_performed'] is False and cleanup['apply_tool_available'] is False
            if release:
                checked=await call('job_reconcile',{'operation_id':identifier,'mode':'release_unstarted',
                    'expected_journal_sha256':checked['journal_sha256']})
                status=await client.call_tool('job_status',{'operation_id':identifier})
                assert not status.isError and status.structuredContent['status']=='cancelled'
            return checked


@pytest.mark.integration
def test_restart_releases_only_proven_unstarted_job_without_replay(tmp_path):
    process=host('queued',tmp_path)
    try:checkpoint=wait_file(tmp_path/(str(process.pid)+'-control.json'))
    finally:process.kill();process.wait(timeout=10)
    identifier=checkpoint['job_id'];journal=tmp_path/'jobs'/identifier/'job.json';sha=digest(journal)
    recovered=asyncio.run(reconcile(tmp_path,identifier,release=True))
    assert recovered['state']=='not_started_released' and digest(journal)==sha
    assert not list(tmp_path.glob('jobs/*/operation.jsx'))
    # A second new MCP process sees the release, never re-admits/replays it.
    assert asyncio.run(reconcile(tmp_path,identifier))['state']=='not_started_released'


@pytest.mark.integration
@pytest.mark.parametrize('phase',['bridge','render','encode'])
def test_interrupted_host_keeps_late_or_partial_work_uncertain(tmp_path,phase):
    process=host(phase,tmp_path)
    try:
        checkpoint=wait_file(tmp_path/'control.json')
        if phase!='bridge':wait_file(tmp_path/'child-alive.json')
    finally:process.kill();process.wait(timeout=10)
    identifier=checkpoint['job_id'];journal=tmp_path/'jobs'/identifier/'job.json';sha=digest(journal)
    if phase=='bridge':wait_file(tmp_path/'jobs'/identifier/'result.json')
    checked=asyncio.run(reconcile(tmp_path,identifier))
    assert checked['safe_release_unstarted'] is False and digest(journal)==sha
    if phase=='bridge':
        assert checked['state']=='late_native_acknowledged_quarantined' and (tmp_path/'ae-pending.json').exists()
    if phase=='render':assert checked['render_quarantine'] and (tmp_path/'preview-pending.json').exists()
    assert not list(tmp_path.glob('projects/*/project.json'))


@pytest.mark.integration
def test_five_hosts_share_four_durable_slots(tmp_path):
    processes=[];ids=[]
    try:
        for _ in range(4):
            process=host('queued',tmp_path);processes.append(process)
            ids.append(wait_file(tmp_path/(str(process.pid)+'-control.json'))['job_id'])
        fifth=host('queued',tmp_path)
        assert fifth.wait(timeout=12)==9
    finally:
        for process in processes:
            if process.poll() is None:process.kill()
            process.wait(timeout=10)
    assert len(ids)==4
    for identifier in ids:assert asyncio.run(reconcile(tmp_path,identifier,True))['released']


@pytest.mark.integration
def test_dependency_report_public_schema_and_saved_scope_without_ae(tmp_path):
    pid='a'*32;directory=tmp_path/'projects'/pid;directory.mkdir(parents=True)
    source=directory/'project.aep';source.write_bytes(b'fixture only, not native AEP'*10)
    before=digest(source)
    state={'footage':[{'ae_id':1,'path':str(tmp_path/'absent.png'),'missing':False}],
        'compositions':[{'layers':[{'text_style':{'font':'FixtureMissing','font_missing':True},'effects':[{'match_name':'Third Party Unverified'}]}]}]}
    write_json(directory/'project.json',dict(status='succeeded',project_id=pid,sha256=before,result={'data':state}))
    async def exercise():
        params=StdioServerParameters(command=sys.executable,args=['-m','astra_video_studio.mcp_server'],env=dict(os.environ,ASTRA_WORKSPACE=str(tmp_path)))
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as client:
                await client.initialize()
                response=await client.call_tool('project_dependencies',{'request':{'project_id':pid}})
                assert not response.isError,response.content
                assert len(encoded(response.model_dump(mode='json',exclude_none=True)))<=8192
                page=await client.call_tool('operation_query',{'request':{'evidence_sha256':response.structuredContent['evidence']['sha256'],'section':'issues','limit':3}})
                assert not page.isError
                assert page.structuredContent['total']==3
                invalid=await client.call_tool('job_reconcile',{'request':{'operation_id':pid,'mode':'release_unstarted'}})
                assert invalid.isError
                invalid=await client.call_tool('workspace_cleanup_plan',{'request':{'operation_ids':[pid],'delete':True}})
                assert invalid.isError
    asyncio.run(exercise())
    assert digest(source)==before and not (tmp_path/'ae-pending.json').exists()
    assert not list(tmp_path.glob('jobs/*/operation.jsx'))
