import os
from typing import Generator, Sequence, Tuple, TypeVar
from operator import itemgetter

from dataclass_csv import DataclassReader
import geopy.distance

from models import EdgeLocation, PopLocation

def read_env(name: str) -> str:
    value = os.getenv(name)
    assert value is not None, f"missing environment var {name}"
    return value


T = TypeVar('T')

def make_chunks(a: Sequence[T], chunk_size: int) -> Generator[Sequence[T], None, None]:
    a = list(a)
    while a:
        chunk, a = a[:chunk_size], a[chunk_size:]
        yield chunk


def flatten(l: list[list[T]]) -> list[T]:
    return [item for sublist in l for item in sublist]


def edge_pop_distance(edge: EdgeLocation, pop: PopLocation) -> float:
    edge_coords = (edge.lat, edge.lon)
    pop_coords = (pop.lat, pop.lon)

    return geopy.distance.geodesic(edge_coords, pop_coords).km


def sort_pops_by_distance(edge: EdgeLocation, pops: list[PopLocation], excluding: str | None = None) -> list[PopLocation]:
    pops_with_distance = [(pop, edge_pop_distance(edge, pop)) for pop in pops if pop.name != excluding]
    return [p for (p, _) in sorted(pops_with_distance, key=itemgetter(1))]


def sort_pops_by_distance_advanced(edge: EdgeLocation, pops: list[PopLocation], excluding: str | None = None) -> list[Tuple[str, float]]:
    pops_with_distance = [(pop.name, edge_pop_distance(edge, pop)) for pop in pops if pop.name != excluding]
    return sorted(pops_with_distance, key=itemgetter(1))

def read_pops(csv_path: str) -> list[PopLocation]:
    res = []
    with open(csv_path, "r") as f:
        reader = DataclassReader(f, PopLocation)

        for r in reader:
            res.append(r)
    return res


def read_edges(csv_path: str) -> list[EdgeLocation]:
    res = []
    with open(csv_path, "r") as f:
        reader = DataclassReader(f, EdgeLocation)

        for r in reader:
            res.append(r)
    return res
