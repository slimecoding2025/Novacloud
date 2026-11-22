import pytest

from novacloud.orchestration.domain import InMemoryJobRepository, Step, Worker, execute_plan, new_job, order_steps


def test_job_retry_then_fail():
    repo = InMemoryJobRepository()
    j, _ = repo.enqueue(new_job("o", "k", {}, "a", max_attempts=2))
    w = Worker(repo, {"k": lambda job: (_ for _ in ()).throw(RuntimeError("boom"))})
    w.run_once(); assert j.status == "queued"
    w.run_once(); assert j.status == "failed" and "boom" in j.error


def test_idempotency_is_per_org():
    repo = InMemoryJobRepository()
    assert repo.enqueue(new_job("o1", "k", {}, "same"))[1] is True
    assert repo.enqueue(new_job("o1", "k", {}, "same"))[1] is False
    assert repo.enqueue(new_job("o2", "k", {}, "same"))[1] is True


def test_plan_orders_dependencies_and_detects_cycles():
    noop = lambda: None  # noqa: E731
    steps = [Step("c", noop, depends_on=("b",)), Step("b", noop, depends_on=("a",)), Step("a", noop)]
    assert [s.name for s in order_steps(steps)] == ["a", "b", "c"]
    with pytest.raises(ValueError):
        order_steps([Step("x", noop, depends_on=("y",)), Step("y", noop, depends_on=("x",))])
    with pytest.raises(ValueError):
        order_steps([Step("x", noop, depends_on=("missing",))])


def test_plan_compensates_in_reverse_on_failure():
    log = []
    def boom(): raise RuntimeError("no")
    steps = [Step("net", lambda: log.append("net"), lambda: log.append("-net")),
             Step("vol", lambda: log.append("vol"), lambda: log.append("-vol"), ("net",)),
             Step("vm", boom, None, ("vol",))]
    r = execute_plan(steps)
    assert r.failed_step == "vm" and r.compensated == ["vol", "net"]
    assert log == ["net", "vol", "-vol", "-net"]
