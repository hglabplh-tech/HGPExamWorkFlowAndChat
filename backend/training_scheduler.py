"""Run curation and training every configured 48-hour interval.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

import asyncio

from .app.config import get_settings
from .training_job import run


async def scheduler() -> None:
    """Run immediately and then wait the configured number of hours between starts."""
    while True:
        await run()
        await asyncio.sleep(get_settings().training_interval_hours * 60 * 60)


if __name__ == "__main__":
    asyncio.run(scheduler())
