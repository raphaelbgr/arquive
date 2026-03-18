"""SSH Orchestrator — bootstraps remote workers via SSH."""

import logging
import subprocess
import threading
import time

from .config import Config

log = logging.getLogger(__name__)


class RemoteWorker:
    """Manages a single remote worker via SSH."""

    def __init__(self, worker_def, coordinator_url: str, project_path: str):
        self.name = worker_def.name
        self.ssh_alias = worker_def.ssh_alias
        self.host = worker_def.host
        self.gpu = worker_def.gpu
        self.coordinator_url = coordinator_url
        self.project_path = project_path
        self.process = None
        self._thread = None

    def start(self):
        """Start the remote worker via SSH."""
        if not self.ssh_alias:
            log.warning("No SSH alias for worker '%s', skipping", self.name)
            return False

        log.info("Starting remote worker '%s' via SSH alias '%s'", self.name, self.ssh_alias)

        # Build the remote command
        # Assumes the project is synced to the remote machine at the same relative path
        # or that the worker script is available
        remote_cmd = (
            f"cd {self.project_path} && "
            f"source venv/bin/activate 2>/dev/null || source venv/Scripts/activate 2>/dev/null && "
            f"python -m face_detect worker "
            f"--name {self.name} "
            f"--coordinator {self.coordinator_url}"
        )

        ssh_cmd = ["ssh", self.ssh_alias, remote_cmd]

        def _run():
            try:
                self.process = subprocess.Popen(
                    ssh_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                for line in self.process.stdout:
                    log.info("[%s] %s", self.name, line.rstrip())
                self.process.wait()
                log.info("Remote worker '%s' exited with code %d",
                         self.name, self.process.returncode)
            except Exception as e:
                log.error("Remote worker '%s' failed: %s", self.name, e)

        self._thread = threading.Thread(target=_run, daemon=True, name=f"worker-{self.name}")
        self._thread.start()
        return True

    def stop(self):
        """Stop the remote worker."""
        if self.process and self.process.poll() is None:
            self.process.terminate()
            log.info("Sent terminate to remote worker '%s'", self.name)

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()


class Orchestrator:
    """Manages starting/stopping remote workers via SSH."""

    def __init__(self, config: Config, coordinator_url: str, project_path: str = "."):
        self.config = config
        self.coordinator_url = coordinator_url
        self.project_path = project_path
        self.remote_workers = []

    def start_remote_workers(self):
        """Start all configured remote workers."""
        for worker_def in self.config.workers:
            if worker_def.host == "localhost" or not worker_def.ssh_alias:
                continue  # Skip local worker

            rw = RemoteWorker(worker_def, self.coordinator_url, self.project_path)
            if rw.start():
                self.remote_workers.append(rw)
                time.sleep(2)  # Stagger starts

        log.info("Started %d remote worker(s)", len(self.remote_workers))

    def stop_all(self):
        """Stop all remote workers."""
        for rw in self.remote_workers:
            rw.stop()
        log.info("All remote workers stopped")

    def status(self) -> list:
        return [
            {"name": rw.name, "alive": rw.is_alive()}
            for rw in self.remote_workers
        ]
