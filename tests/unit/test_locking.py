import os
import threading

import pytest

from astra_video_studio.ae_bridge.locking import AELock


@pytest.mark.skipif(os.name != "nt", reason="Windows session mutex")
def test_mutex_blocks_other_thread():
    outcomes = []
    def contend():
        try:
            with AELock():
                outcomes.append("acquired")
        except BlockingIOError:
            outcomes.append("blocked")
    with AELock():
        thread = threading.Thread(target=contend)
        thread.start()
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert outcomes == ["blocked"]
    with AELock():
        pass
