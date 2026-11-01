import time

from PySide6.QtCore import QCoreApplication

from attractr.core.jobs.cancel import CancelToken
from attractr.core.jobs.job import FunctionJob
from attractr.core.jobs.queue import JobQueue


def _app():
    return QCoreApplication.instance() or QCoreApplication([])


def test_function_job_sync():
    job = FunctionJob(lambda c, t: 42, "answer")
    got = []
    job.finished.connect(got.append)
    assert job.execute() == 42
    assert got == [42] and job.state == "done"


def test_job_failure_is_reported():
    def boom(c, t):
        raise ValueError("x")

    job = FunctionJob(boom)
    errs = []
    job.failed.connect(errs.append)
    assert job.execute() is None
    assert job.state == "failed" and "ValueError" in errs[0]


def test_cancel_token_stops_job():
    def work(cancel: CancelToken, tracker):
        for i in range(1000):
            cancel.check()
            tracker.update(i / 1000)
            time.sleep(0.001)
        return "done"

    job = FunctionJob(work)
    job.cancel()
    assert job.execute() is None and job.state == "cancelled"


def test_queue_runs_jobs_in_threads():
    app = _app()
    q = JobQueue(max_concurrent=2)
    results = []
    jobs = [FunctionJob(lambda c, t, i=i: i * i, f"j{i}") for i in range(4)]
    for j in jobs:
        j.finished.connect(results.append)
        q.submit(j)
    deadline = time.time() + 5
    while not q.is_idle and time.time() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert q.is_idle
    app.processEvents()
    assert sorted(results) == [0, 1, 4, 9]
