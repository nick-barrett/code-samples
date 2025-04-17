import os
from typing import Any, Generator, Optional, Sequence


def read_env(name: str) -> str:
    value = os.getenv(name)
    assert value is not None, f"missing environment var {name}"
    return value


def make_chunks[T](
    a: Sequence[T], chunk_size: int
) -> Generator[Sequence[T], None, None]:
    a = list(a)
    while a:
        chunk, a = a[:chunk_size], a[chunk_size:]
        yield chunk


def extract_module(module_list: list[dict], module_name: str) -> Optional[dict]:
    return next((m for m in module_list if m["name"] == module_name), None)


def dict_query(d: dict[str, Any], query: str) -> Optional[Any]:
    keys = query.split(".")
    for key in keys:
        if isinstance(d, dict) and key in d:
            d = d[key]
        else:
            return None

    return d


def json_query(o: dict[str, Any] | list[Any], query: str) -> Optional[Any]:
    keys = query.split(".")
    for key in keys:
        if isinstance(o, dict) and key in o:
            o = o[key]
        elif isinstance(o, list) and key.isdigit():
            o = o[int(key)]
        else:
            return None

    return o
