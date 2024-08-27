import concurrent.futures
import os


def qimap(func, *iterables):
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=int(os.getenv("QY_MAX_WORKERS",
                        min(32, os.cpu_count() + 4)))
    ) as executor:
        yield from executor.map(func, *iterables)


def qmap(func, *iterables):
    return list(qimap(func, *iterables))


def join(separator: str, *iterables: list[str]) -> str:
    return separator.join(iterables)
