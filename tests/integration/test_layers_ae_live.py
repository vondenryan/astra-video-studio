"""Opt-in MVP layer/media tools and multi-layer stagger through the real MCP server."""
import asyncio
import os
from pathlib import Path
import struct
import sys
from uuid import uuid4
import zlib

from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
import pytest
from astra_video_studio.config import Settings


@pytest.mark.ae_live
@pytest.mark.skipif(os.environ.get('ASTRA_RUN_AE_TESTS')!='1',reason='Opt-in layer/media AE integration')
def test_layer_types_media_copy_and_stagger():
    settings=Settings.from_env()
    directory=settings.contained_path('fixtures/'+uuid4().hex); directory.mkdir(parents=True,exist_ok=False)
    asset=directory/'swatch.png'
    def chunk(kind,data): return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',32,16,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+bytes([35,180,240])*32)*16))+chunk(b'IEND',b'')
    asset.write_bytes(png)
    async def exercise():
        params=StdioServerParameters(command=sys.executable,args=['-m','astra_video_studio.mcp_server'],env=dict(os.environ))
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize()
                async def call(name,request):
                    response=await session.call_tool(name,{'request':request})
                    assert not response.isError,response.content
                    result=response.structuredContent
                    assert result['status']=='succeeded',result
                    return result
                created=await call('project_create',{'name':'Astra MVP Layer Tools','width':640,'height':360,'fps':24,'duration':3,'font_size':32})
                original=Path(created['project_path']).read_bytes()
                target={'project_id':created['project_id'],'composition_id':created['data']['compositions'][0]['composition_id'].split(':')[-1]}
                text=await call('layer_create',target|{'layer':{'kind':'text','name':'Subtitle','text':'LOCAL • EDITÁVEL','font_size':24,'position':[320,250]}})
                shape=await call('layer_create',target|{'layer':{'kind':'shape','name':'Circle','shape':'ellipse','size':[80,80],'position':[100,100]}})
                await call('layer_create',target|{'layer':{'kind':'solid','name':'Footer','size':[640,30],'position':[320,340],'opacity':30}})
                imported=await call('media_import',{'project_id':created['project_id'],'source_path':str(asset)})
                assert Path(imported['data']['asset_path']).read_bytes()==png
                assert imported['data']['imported_asset']['width']==32
                await call('layer_create',target|{'layer':{'kind':'media','name':'Imported swatch','asset_id':imported['data']['asset_id'],'position':[550,80]}})
                staggered=await call('stagger_layers',target|{'layer_ids':[text['data']['layer_id'],shape['data']['layer_id']],'skill':'scale_pop','start_time':0.2,'duration':0.6,'interval':0.1,'params':{'initial_scale':80,'overshoot':0.02}})
                assert len(staggered['data']['compositions'][0]['layers'])==5
                assert asset.read_bytes()==png and Path(created['project_path']).read_bytes()==original
    asyncio.run(asyncio.wait_for(exercise(),timeout=300))
