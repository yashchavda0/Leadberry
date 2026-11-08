import asyncio


def selector_event_loop() -> asyncio.AbstractEventLoop:
    """Uvicorn loop factory: psycopg async cannot run on Windows' ProactorEventLoop."""
    return asyncio.SelectorEventLoop()
