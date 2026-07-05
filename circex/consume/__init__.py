"""Live consumer: process every incoming GCN circular into SkyPortal."""

from circex.consume.processor import ProcessResult, process_circular, run
from circex.consume.sources import dir_fetch, gcn_kafka_records, replay_dir_records

__all__ = [
    "ProcessResult",
    "dir_fetch",
    "gcn_kafka_records",
    "process_circular",
    "replay_dir_records",
    "run",
]
