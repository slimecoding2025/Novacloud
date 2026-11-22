"""Prometheus text exposition written by hand. Every metric declares its real source; if a source
cannot be read the metric is reported as unavailable (nc_metric_available 0), never as zero."""
from dataclasses import dataclass
from collections.abc import Callable


@dataclass
class Metric:
    name: str
    help: str
    source: str
    kind: str  # gauge | counter
    collect: Callable[[], float | dict[tuple, float]]
    labels: tuple[str, ...] = ()


def _esc(v: str) -> str:
    return str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


class MetricsRegistry:
    def __init__(self):
        self.metrics: list[Metric] = []
        self._counters: dict[tuple[str, tuple], float] = {}

    def register(self, m: Metric) -> None:
        self.metrics.append(m)

    def inc(self, name: str, labels: tuple = (), by: float = 1.0) -> None:
        self._counters[(name, labels)] = self._counters.get((name, labels), 0.0) + by

    def counter_metric(self, name: str, help: str, source: str, labels: tuple[str, ...] = ()) -> None:
        def collect(n=name):
            return {lv: v for (nm, lv), v in self._counters.items() if nm == n} or {tuple("" for _ in labels): 0.0}
        self.register(Metric(name, help, source, "counter", collect, labels))

    def render(self) -> str:
        out, avail = [], []
        for m in self.metrics:
            try:
                data = m.collect()
            except Exception:  # noqa: BLE001 - an unreadable source is "unavailable", not zero
                avail.append(f'novacloud_metric_available{{metric="{m.name}",source="{_esc(m.source)}"}} 0')
                continue
            avail.append(f'novacloud_metric_available{{metric="{m.name}",source="{_esc(m.source)}"}} 1')
            out += [f"# HELP {m.name} {m.help} (source: {m.source})", f"# TYPE {m.name} {m.kind}"]
            items = data.items() if isinstance(data, dict) else [((), data)]
            for lv, v in items:
                lab = ",".join(f'{k}="{_esc(x)}"' for k, x in zip(m.labels, lv, strict=False))
                out.append(f"{m.name}{{{lab}}} {v}" if lab else f"{m.name} {v}")
        out += ["# HELP novacloud_metric_available 1 if the metric source could be read, 0 if unavailable",
                "# TYPE novacloud_metric_available gauge", *avail]
        return "\n".join(out) + "\n"
