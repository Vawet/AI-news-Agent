"""Run the long-lived SAE service."""

import logging
import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import settings
from src.runtime.service import create_app


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )
    uvicorn.run(
        create_app(),
        host=settings.service_host,
        port=settings.service_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
