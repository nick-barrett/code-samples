from typing import Optional, Callable
import itertools
import json
import dataclasses

from dataclass_csv import DataclassWriter

from models import (
    PopLocation,
    EdgeLocation,
    PopPair,
    PopTotal,
    NetworkPartition,
    Gateway,
    Pop,
    Edge,
    NetworkPartitionOutput,
    GatewayOutput,
    PopOutput,
    EdgeOutput,
)
from util import read_edges, read_pops, sort_pops_by_distance, make_chunks

GW_TUNNEL_SCALE = 3000
GW_TUNNEL_SCALE_TARGET_FACTOR = 0.9

GROWTH_FACTOR = 0.1

LINKS_PER_BRANCH = 2
HUBS_PER_PARTITION = 6
LINKS_PER_HUB = 1

CHUNK_SIZE = 1

def find_pop(pop_name: str, pops: list[PopLocation]) -> Optional[PopLocation]:
    return next(iter([p for p in pops if p.name == pop_name]), None)


def compute_pop_pair_map(
    edges: list[EdgeLocation], pops: list[PopLocation]
) -> dict[tuple[str, str], list[EdgeLocation]]:
    pop_pair_map: dict[tuple[str, str], list[EdgeLocation]] = dict()

    for edge in edges:
        pri, sec, *_ = sort_pops_by_distance(edge, pops)

        pop_pair = (pri.name, sec.name)
        if pop_pair in pop_pair_map:
            pop_pair_map[pop_pair].append(edge)
        else:
            pop_pair_map[pop_pair] = [edge]

    return pop_pair_map


def grow_pop_pairs(pop_pair_list: list[PopPair], growth_factor: float):
    edge_index = 0
    for pair in pop_pair_list:
        new_edge_index = edge_index + int(len(pair.edges) * growth_factor)
        pair.edges.extend(
            [
                EdgeLocation(f"future-{index}", 0, 0)
                for index in range(edge_index, new_edge_index)
            ]
        )
        edge_index = new_edge_index


def compute_pop_total_map(pop_pair_list: list[PopPair]) -> dict[str, int]:
    pop_total_map: dict[str, int] = {n: 0 for p in pop_pair_list for n in [p.pri, p.sec]}

    for pair in pop_pair_list:
        edge_count = len(pair.edges)

        pop_total_map[pair.pri] += edge_count
        pop_total_map[pair.sec] += edge_count

    return pop_total_map


def compute_pop_total_list(
    pop_pair_list: list[PopPair], gateway_tunnel_target: int
) -> list[PopTotal]:
    pop_totals = [
        PopTotal(name, count)
        for (name, count) in compute_pop_total_map(pop_pair_list).items()
    ]

    for pop in pop_totals:
        pop.tunnel_count = (
            pop.edge_count * LINKS_PER_BRANCH + HUBS_PER_PARTITION * LINKS_PER_HUB
        )
        # round up
        pop.gateway_count = max(
            int((pop.tunnel_count / gateway_tunnel_target) + 0.5), 1
        )

    return pop_totals


def main():
    edges = read_edges("edges.csv")
    pops = read_pops("pops.csv")

    pop_pair_map = compute_pop_pair_map(edges, pops)

    pop_pair_list = [
        PopPair(pri, sec, edges) for ((pri, sec), edges) in pop_pair_map.items()
    ]

    #grow_pop_pairs(pop_pair_list, GROWTH_FACTOR)

    gateway_tunnel_scale_target = int(GW_TUNNEL_SCALE * GW_TUNNEL_SCALE_TARGET_FACTOR)
    pop_total_list = compute_pop_total_list(pop_pair_list, gateway_tunnel_scale_target)

    with open("out/pop-totals.csv", "w") as f:
        w = DataclassWriter(f, list(pop_total_list), PopTotal)
        w.write()

    partitions = {
        "A": NetworkPartition("A", dict(), dict(), 0, 0, dict()),
        "B": NetworkPartition("B", dict(), dict(), 0, 0, dict()),
    }

    gateway_index = 1
    odd_gateway_part_cycle = itertools.cycle(partitions.values())
    for pop in pop_total_list:
        gateway_count = pop.gateway_count
        new_gateway_index = gateway_index + gateway_count

        part_iterator = (
            itertools.cycle(partitions.values())
            if gateway_count % len(partitions) == 0
            else odd_gateway_part_cycle
        )

        for gw_index, p in zip(
            range(gateway_index, new_gateway_index),
            part_iterator,
        ):
            p.gateways[gw_index] = Gateway(gw_index, pop.name, 0)

            if pop.name not in p.pops:
                p.pops[pop.name] = Pop(pop.name, 1, [gw_index])
            else:
                p.pops[pop.name].gateways.append(gw_index)
                p.pops[pop.name].gateway_count += 1

        gateway_index = new_gateway_index

    for part in partitions.values():
        part.gateway_count = len(part.gateways)

    chunk_size = CHUNK_SIZE
    total_edges_assigned = 1

    for pair in pop_pair_list:
        for edges_chunk in make_chunks(pair.edges, chunk_size):
            candidate_parts = [
                p
                for p in partitions.values()
                if pair.pri in p.pops and pair.sec in p.pops
            ]

            part = find_best_partition(candidate_parts, pair, total_edges_assigned)

            pri_gateway = find_best_gateway(part, pair.pri)
            sec_gateway = find_best_gateway(part, pair.sec)

            part.edges.update(
                {
                    e.name: Edge(
                        e.name,
                        pri_gateway.index,
                        sec_gateway.index,
                    )
                    for e in edges_chunk
                }
            )

            edge_count = len(edges_chunk)
            part.edge_count += edge_count
            pri_gateway.edge_count += edge_count
            sec_gateway.edge_count += edge_count

            total_edges_assigned += edge_count

    per_pop_id_index: dict[str, int] = dict()
    pop_gw_names: dict[int, str] = dict()

    for part in partitions.values():
        for index, gw in part.gateways.items():
            if gw.pop not in per_pop_id_index:
                per_pop_id_index[gw.pop] = 1

            pop_gw_names[index] = f"{gw.pop}-{per_pop_id_index[gw.pop]}"
            per_pop_id_index[gw.pop] += 1

    partitions_out = [
        NetworkPartitionOutput(
            p.name,
            [PopOutput(pop.name, pop.gateway_count) for pop in p.pops.values()],
            [
                GatewayOutput(pop_gw_names[gw.index], gw.edge_count)
                for gw in p.gateways.values()
            ],
            p.gateway_count,
            p.edge_count,
            [
                EdgeOutput(
                    e.name, pop_gw_names[e.primary_gw], pop_gw_names[e.secondary_gw]
                )
                for e in p.edges.values()
            ],
        )
        for p in partitions.values()
    ]

    with open("out/results.json", "w") as f:
        json.dump(
            list([dataclasses.asdict(p) for p in partitions_out]), f, indent=2
        )


def find_best_partition(
    partitions: list[NetworkPartition], pair: PopPair, num_edges_assigned: int
) -> NetworkPartition:
    return min(partitions, key=get_best_partition_key_fn(pair, num_edges_assigned))


# generate a closure that captures the pop pair
def get_best_partition_key_fn(
    pair: PopPair, num_edges_assigned: int
) -> Callable[[NetworkPartition], float]:
    # calculates average edges per gateway for the primary + secondary PoP in this partition
    # need to also weight against the fraction of edges in the partition vs total edge count
    return (
        lambda part: (
            sum(
                [
                    part.gateways[i].edge_count * LINKS_PER_BRANCH
                    for i in part.pops[pair.pri].gateways
                ]
            )
            / (len(part.pops[pair.pri].gateways) * GW_TUNNEL_SCALE * GW_TUNNEL_SCALE_TARGET_FACTOR)
        )
        + (
            sum(
                [
                    part.gateways[i].edge_count * LINKS_PER_BRANCH
                    for i in part.pops[pair.sec].gateways
                ]
            )
            / (len(part.pops[pair.sec].gateways) * GW_TUNNEL_SCALE * GW_TUNNEL_SCALE_TARGET_FACTOR)
        )
        + 0.5 * (part.edge_count / num_edges_assigned)
    )


def find_best_gateway(partition: NetworkPartition, pop: str) -> Gateway:
    gateways = [gw for gw in partition.pops[pop].gateways]
    return min(
        [partition.gateways[gw_index] for gw_index in gateways],
        key=lambda gw: gw.edge_count,
    )


if __name__ == "__main__":
    main()
