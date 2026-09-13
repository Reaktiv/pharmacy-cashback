"""Overrides Django's `runserver` for the host `.venv` dev workflow (README's
"Running locally against a .venv" section): a single `python manage.py
runserver` now also brings up the Docker services the backend depends on
(Postgres, Redis, the Celery worker/beat) and defaults to port 8010 instead
of Django's usual 8000, so there's no separate `docker compose up -d db
redis` step to remember.

Skipped entirely when already running *inside* a container (detected via
/.dockerenv) — docker-compose.yml's own `web` service already gets db/redis
via `depends_on`, and there's no Docker socket to drive from in there anyway.

Also skipped when RUN_MAIN=true: the autoreloader re-executes this whole
command from scratch in a fresh child process (with RUN_MAIN set) every time
it launches or restarts the dev server after a code change — running
`docker compose up` again in the child raced with the parent's own run in
testing and made the `beat` container exit non-zero. RUN_MAIN is unset only
in the one outer, pre-reload process, so that's the only place this runs.
"""

import os
import subprocess
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles.management.commands.runserver import (
    Command as StaticfilesRunserverCommand,
)

DOCKER_DEPENDENCIES = ["db", "redis", "worker", "beat"]


class Command(StaticfilesRunserverCommand):
    default_port = "8010"

    def handle(self, *args, **options):
        if os.environ.get("RUN_MAIN") != "true" and not Path("/.dockerenv").exists():
            self._start_docker_dependencies()
        super().handle(*args, **options)

    def _start_docker_dependencies(self):
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"Starting docker dependencies ({', '.join(DOCKER_DEPENDENCIES)})..."
            )
        )
        try:
            subprocess.run(
                ["docker", "compose", "up", "-d", "--wait", *DOCKER_DEPENDENCIES],
                cwd=settings.REPO_ROOT,
                check=True,
            )
        except FileNotFoundError:
            self.stderr.write(
                self.style.ERROR(
                    "docker not found on PATH — install Docker or start "
                    f"{', '.join(DOCKER_DEPENDENCIES)} yourself before running this."
                )
            )
        except subprocess.CalledProcessError as exc:
            self.stderr.write(self.style.ERROR(f"docker compose up failed: {exc}"))
