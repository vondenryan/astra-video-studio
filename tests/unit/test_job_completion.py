from concurrent.futures import Future
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from astra_video_studio.config import Settings
from astra_video_studio.jobs import Job, write_json
from astra_video_studio.media.preview import PreviewService
from astra_video_studio.project_manager import ProjectManager


def test_atomic_json_retries_transient_windows_sharing(tmp_path):
    path = tmp_path / 'state.json'; write_json(path, {'old': True})
    replace = Path.replace; attempts = []
    def sharing(source, destination):
        attempts.append(1)
        if len(attempts) < 3:
            assert json.loads(path.read_text()) == {'old': True}
            raise PermissionError('simulated Windows reader')
        return replace(source, destination)
    with patch.object(Path, 'replace', sharing), patch('astra_video_studio.jobs.time.sleep'):
        write_json(path, {'new': True})
    assert len(attempts) == 3 and json.loads(path.read_text()) == {'new': True}


def test_atomic_json_permanent_denial_keeps_prior_file(tmp_path):
    path = tmp_path / 'state.json'; write_json(path, {'old': True})
    with patch.object(Path, 'replace', side_effect=PermissionError('persistent')), patch('astra_video_studio.jobs.time.sleep'):
        with pytest.raises(PermissionError): write_json(path, {'new': True})
    assert json.loads(path.read_text()) == {'old': True}


def test_worker_completion_failure_is_durable_and_visible(tmp_path):
    settings = Settings(tmp_path); job = Job(settings, 'preview_render'); job.record('running')
    future = Future(); future.set_exception(PermissionError('final journal locked'))
    with patch.object(job, 'record', side_effect=PermissionError('main journal still locked')):
        PreviewService._worker_completed(job, future)
    assert json.loads((job.directory / 'job.json').read_text())['status'] == 'running'
    result = ProjectManager(settings).job_status(job.id)
    assert result['status'] == 'failed' and 'PermissionError' in result['result']['error']
    assert (job.directory / 'worker-failure.json').is_file()


def test_worker_finalization_always_releases_slot(tmp_path):
    settings = Settings(tmp_path); job = Job(settings, 'preview_render')
    (job.directory / 'cancel-requested').touch()
    with patch.object(job, 'record', side_effect=PermissionError('final journal')), patch('astra_video_studio.media.preview._slots') as slots:
        with pytest.raises(PermissionError): PreviewService(settings)._work(job, Mock(project_id='1' * 32), tmp_path / 'unused.aep', 'unused', None, {})
        slots.release.assert_called_once()


def test_cancelled_future_releases_slot_without_entering_worker(tmp_path):
    job = Job(Settings(tmp_path), 'preview_render'); future = Future(); future.cancel()
    with patch('astra_video_studio.media.preview._slots') as slots:
        PreviewService._worker_completed(job, future)
        slots.release.assert_called_once()
    assert json.loads((job.directory / 'job.json').read_text())['status'] == 'failed'
