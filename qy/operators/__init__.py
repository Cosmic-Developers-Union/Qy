import concurrent.futures
import os


def qimap(func, *iterables):
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=int(os.getenv("QY_MAX_WORKERS", min(32, (os.cpu_count() or 1) + 4)))
    ) as executor:
        yield from executor.map(func, *iterables)


def qmap(func, *iterables):
    return list(qimap(func, *iterables))


def join(separator: str, *strings: str) -> str:
    return separator.join(strings)
