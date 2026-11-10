"""Inventory the target-filtered Cargo graph; this is not a legal clearance."""
import json
from pathlib import Path
import sys
from astra_video_studio.config import Settings
from astra_video_studio.existing_projects import digest
from astra_video_studio.jobs import write_json


def inspect_graph(metadata):
    nodes={row['id']:row for row in metadata['resolve']['nodes']}
    seen=set();stack=[metadata['resolve']['root']]
    while stack:
        current=stack.pop()
        if current in seen:continue
        seen.add(current);stack.extend(row['pkg'] for row in nodes[current]['deps'])
    packages=[row for row in metadata['packages'] if row['id'] in seen]
    gui_prefixes=('egui','eframe','winit','gtk','iced','tao','wry','fltk','slint','effectcraft-ui')
    gui=[row['name'] for row in packages if row['name'].startswith(gui_prefixes)]
    return {'target':'x86_64-pc-windows-msvc','reachable_package_count':len(packages),'gui_packages':gui,
        'license_status':'Manifest inventory only; full license/notice/SBOM gate remains pending',
        'packages':[{'name':p['name'],'version':p['version'],'license':p['license'],'source':p['source'],
            'features':nodes[p['id']]['features']} for p in packages]}


if __name__=='__main__':
    source,target=map(Path,sys.argv[1:])
    result=inspect_graph(json.loads(source.read_text(encoding='utf-8-sig')))
    result.update(metadata_sha256=digest(source),cargo_lock_sha256=digest(Path(__file__).parent/'worker/Cargo.lock'))
    write_json(target,result)
    print(json.dumps({k:v for k,v in result.items() if k!='packages'}))
    if result['gui_packages']:raise SystemExit('GUI graph gate failed')
    write_json(Settings.from_env().contained_path('ec0/dependencies-current.json'),
        {'closure_path':str(target),'closure_sha256':digest(target),'metadata_path':str(source)})
