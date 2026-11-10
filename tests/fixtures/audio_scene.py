"""Synthetic owned audio and optional fake saved-state metadata; never opens AE."""
from array import array
import math
from pathlib import Path
import sys
import wave

from astra_video_studio.existing_projects import digest
from astra_video_studio.jobs import write_json

PID, CID, LID = '3'*32, '2'*32, '1'*32


def write_tone(path, duration, amplitude=1000, pulse=False):
    with wave.open(str(path), 'wb') as output:
        output.setparams((2, 2, 48000, 0, 'NONE', 'not compressed'))
        for first in range(0, int(duration*48000), 4800):
            values = array('h')
            for n in range(first, min(first+4800, int(duration*48000))):
                value = int(amplitude*math.sin(2*math.pi*440*n/48000)) if not pulse or n < 4800 else 0
                values.extend([value, value])
            if sys.byteorder != 'little': values.byteswap()
            output.writeframes(values.tobytes())


def fake_project(workspace):
    directory = Path(workspace)/'projects'/PID
    directory.mkdir(parents=True)
    source = directory/'project.aep'
    source.write_bytes(b'FIXTURE ONLY - NOT AN AE PROJECT\0'*10)
    comp = {'composition_id': 'astra:composition:'+CID, 'width': 320, 'height': 180, 'fps': 24, 'duration': 20,
        'layers': [{'layer_id': 'astra:layer:'+LID, 'transforms': {'opacity': {
            'expression_enabled': False, 'expression_present': False,
            'keys': [{'time': t, 'value': v} for t,v in [(0,0),(3,100),(10,100),(20,0)]]}}}]}
    write_json(directory/'project.json', {'project_id': PID, 'status': 'succeeded', 'sha256': digest(source),
        'result': {'data': {'fixture_only': True, 'compositions': [comp]}}})
    return source, comp
