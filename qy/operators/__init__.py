import concurrent.futures


def qimap(func, *iterables):
    with concurrent.futures.ThreadPoolExecutor() as executor:
        yield from executor.map(func, *iterables)


def qmap(func, *iterables):
    return list(qimap(func, *iterables))


def join(separator: str, *iterables: list[str]) -> str:
    return separator.join(iterables)
