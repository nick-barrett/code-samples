"""
Process a CSV of edge profile swaps and apply them.
"""

import argparse
import asyncio
from dataclasses import dataclass
import logging
import time
import random
from typing import Tuple
import aiohttp

from dataclass_csv import DataclassReader, DataclassWriter
import dotenv

from veloapi.api import get_enterprise_edges_v1, get_enterprise_events_list, set_edge_enterprise_configuration
from veloapi.models import CommonData
from veloapi.util import make_chunks, read_env

@dataclass
class EdgeAssn:
    id: int
    name: str
    current_profile_id: int
    current_profile_name: str
    new_profile_id: int | None = None
    new_profile_name: str | None = None

def update_edge_profile_shim(shared: CommonData, assn: EdgeAssn) -> bool:
    logging.debug("shim edge profile swap starting")
    time.sleep(4)
    if random.random() < 0.05:
        raise ValueError("shim edge profile swap exception generated for testing")
    logging.debug("shim edge profile swap completed")
    return True


async def update_edge_profile_real(shared: CommonData, assn: EdgeAssn):
    if assn.new_profile_id is None:
        raise ValueError("edge assignment new_profile_id is None")

    logging.debug("real edge profile swap API call starting")
    await set_edge_enterprise_configuration(shared, assn.id, assn.new_profile_id)
    logging.debug("real edge profile swap API call completed")


async def update_edge_profile(
    shared: CommonData, assn: EdgeAssn, dry_run: bool = True
) -> Tuple[EdgeAssn, bool]:
    # ensure the profile ID provided is good
    if (
        assn.new_profile_id is None
        or not isinstance(assn.new_profile_id, int)
        or assn.new_profile_id <= 0
    ):
        logging.info(f"no profile id provided for edge [ {assn.name} ]")
        return (assn, False)

    try:
        logging.debug("edge profile swap starting")
        if not dry_run:
            await update_edge_profile_real(shared, assn)
        else:
            update_edge_profile_shim(shared, assn)
        return (assn, True)
    except Exception:
        logging.exception("edge profile swap exception")
        return (assn, False)
    finally:
        logging.debug("edge profile swap completed")


def read_edge_assignments(filename: str) -> list[EdgeAssn]:
    result = []

    with open(filename, "r") as f:
        r = DataclassReader(f, EdgeAssn)
        for row in r:
            result.append(row)

    return result


async def main(
    env_file: str | None,
    edge_assn_path: str,
    dry_run: bool,
    session: aiohttp.ClientSession,
):
    if env_file:
        dotenv.load_dotenv(env_file, verbose=True, override=True)

    shared = CommonData(
        read_env("VCO"), read_env("VCO_TOKEN"), int(read_env("ENT_ID")), session
    )

    edge_assn = read_edge_assignments(edge_assn_path)
    edge_assn_count = len(edge_assn)

    logging.info(f"{edge_assn_count} edge assignments loaded")
    if "continue" != input("Type continue and press enter to proceed: "):
        logging.info("continue not received. exiting.")
        return

    config_batch_size = 5

    assignments_processed = 0
    failed_assns = []
    completed_assns = []
    start_time = time.time()

    logging.info("entering configuration stage")

    try:
        for chunk in make_chunks(edge_assn, config_batch_size):
            tasks = []
            for assn in chunk:
                tasks.append(
                    asyncio.ensure_future(update_edge_profile(shared, assn, dry_run))
                )

            task_results = await asyncio.gather(*tasks)
            for assn, succeeded in task_results:
                if not succeeded:
                    failed_assns.append(assn)

                    logging.error(
                        "total failure count = [{}]".format(len(failed_assns))
                    )
                else:
                    completed_assns.append(assn)

            assignments_processed += len(task_results)
            time_passed = time.time() - start_time
            pct_done = (100.0 * assignments_processed) / edge_assn_count

            # estimation math for remaining time to process rest of assignments
            time_remaining = (
                (float(edge_assn_count) / float(assignments_processed)) - 1.0
            ) * time_passed
            # split remaining time into hr, min, sec
            min_rem, sec_rem = divmod(int(time_remaining), 60)
            hr_rem, min_rem = divmod(min_rem, 60)

            logging.info(
                "[{:4d} of {:4d}] [{:5.1f}%] [{:02d}:{:02d}:{:02d} remaining]".format(
                    assignments_processed,
                    edge_assn_count,
                    pct_done,
                    hr_rem,
                    min_rem,
                    sec_rem,
                )
            )
    except KeyboardInterrupt:
        logging.exception("ctrl-c received")
    except Exception:
        logging.exception("exception occured during assignment loop")

    csv_name_timestamp = int(time.time_ns() / 1000)
    failed_assn_count = len(failed_assns)
    completed_assn_count = len(completed_assns)

    if failed_assn_count > 0:
        timestamp = csv_name_timestamp
        failed_assn_path = f"failed_assns_{timestamp}.csv"

        logging.info(
            f"{failed_assn_count} failed assignments will be written to {failed_assn_path}"
        )

        with open(failed_assn_path, "w") as f:
            w = DataclassWriter(f, failed_assns, EdgeAssn)
            w.write()
    else:
        logging.info("no failed assignments")

    if completed_assn_count > 0:
        timestamp = csv_name_timestamp
        completed_assn_path = f"completed_assns_{timestamp}.csv"

        logging.info(
            f"{completed_assn_count} completed assignments will be written to {completed_assn_path}"
        )

        with open(completed_assn_path, "w") as f:
            w = DataclassWriter(f, completed_assns, EdgeAssn)
            w.write()
    else:
        logging.info("no completed assignments")

    validation_start_secs = time.time()
    logging.info(
        "configuration stage took {} seconds".format(
            int(validation_start_secs - start_time)
        )
    )

    logging.info("entering validation stage")

    # convert start_time from seconds to milliseconds for get_enterprise_events_list API
    start_time = int(start_time * 1000)
    # get set of edge IDs that were input to be assigned
    edge_assn_ids = set((e.id for e in edge_assn))

    logging.info("checking how many edges are online")
    all_edges = await get_enterprise_edges_v1(shared)
    online_edge_ids = set(
        (
            id
            for e in all_edges
            if (e.get("edgeState", "") == "CONNECTED" or e.get("edgeState", "") == "DEGRADED")
            and (id := e.get("id", None)) is not None
            and id in edge_assn_ids
        )
    )
    online_edge_count = len(online_edge_ids)
    offline_edge_ids = set(
        (
            id
            for e in all_edges
            if (e.get("edgeState", "") != "CONNECTED" and e.get("edgeState", "") != "DEGRADED")
            and (id := e.get("id", None)) is not None
            and id in edge_assn_ids
        )

    )
    offline_edge_count = len(offline_edge_ids)
    if offline_edge_count > 0:
        offline_edges = [e for e in edge_assn if e.id in offline_edge_ids]

        offline_assn_path = f"offline_assns_{csv_name_timestamp}.csv"

        logging.info(
            f"{offline_edge_count} offline edges will be written to {offline_assn_path}"
        )

        with open(offline_assn_path, "w") as f:
            w = DataclassWriter(f, offline_edges, EdgeAssn)
            w.write()

    logging.info(f"{online_edge_count} edges online")

    max_validation_secs = 3 * 60
    validation_sleep_duration = 10

    # don't validate if not a real run
    while not dry_run:
        events = await get_enterprise_events_list(
            shared,
            {
                "and": [
                    {
                        "field": "message",
                        "operator": "contains",
                        "value": "Applied new configuration for deviceSettings version",
                    }
                ]
            },
            start_time,
        )

        # remove any events for edges outside this run or for offline edges
        events = [e for e in events if e.edge_id in online_edge_ids]
        event_count = len(events)
        pct_done = 100.0 * event_count / online_edge_count

        logging.info(
            "[{:4d} of {:4d}] [{:5.1f}%] configurations validated.".format(
                event_count, online_edge_count, pct_done
            )
        )

        validation_secs_elapsed = int(time.time() - validation_start_secs)

        if event_count >= online_edge_count:
            logging.info("all online edges validated. ending validation.")
            # get the set of edge ID's that are validated by events
            event_edge_ids = set((e.edge_id for e in events))
            # get the full edge assignment object based on event-validated edge IDs
            unvalidated_online_edges = [
                e
                for e in edge_assn
                if e.id not in event_edge_ids and e.id in online_edge_ids
            ]

            # only log if there are some unvalidated online edges
            if len(unvalidated_online_edges) > 0:
                unvalidated_assn_path = f"unvalidated_assns_{csv_name_timestamp}.csv"

                logging.info(
                    f"unvalidated assignments will be written to {unvalidated_assn_path}"
                )

                with open(unvalidated_assn_path, "w") as f:
                    w = DataclassWriter(f, unvalidated_online_edges, EdgeAssn)
                    w.write()
            else:
                logging.info(
                    "all online edges validated. shouldn't be seeing this message."
                )
            break
        elif validation_secs_elapsed > max_validation_secs:
            logging.info(
                "more than {} seconds spend validating. ending validation.".format(
                    max_validation_secs
                )
            )

            # get the set of edge ID's that are validated by events
            event_edge_ids = set((e.edge_id for e in events))
            # get the full edge assignment object based on event-validated edge IDs
            unvalidated_online_edges = [
                e
                for e in edge_assn
                if e.id not in event_edge_ids and e.id in online_edge_ids
            ]

            # only log if there are some unvalidated online edges
            if len(unvalidated_online_edges) > 0:
                unvalidated_assn_path = f"unvalidated_assns_{csv_name_timestamp}.csv"

                logging.info(
                    f"unvalidated assignments will be written to {unvalidated_assn_path}"
                )

                with open(unvalidated_assn_path, "w") as f:
                    w = DataclassWriter(f, unvalidated_online_edges, EdgeAssn)
                    w.write()
            else:
                logging.info(
                    "all online edges validated. shouldn't be seeing this message."
                )

            # stop validation loop
            break

        await asyncio.sleep(validation_sleep_duration)

    logging.info(f"finished assignments in {edge_assn_path}. exiting...")


async def async_main(env_file: str | None, edge_assn_path: str, dry_run: bool):
    async with aiohttp.ClientSession() as session:
        await main(env_file, edge_assn_path, dry_run, session)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-e", "--env", type=str, help="Environment variable filename")
    parser.add_argument(
        "-i",
        "--input-csv-filename",
        type=str,
        dest="input_csv",
        help="Filename of CSV assignment list",
        required=True,
    )
    parser.add_argument(
        "--apply-to-vco",
        action="store_false",
        help="Perform a live run on input CSV and push changes to the VCO. By default, a dry run is done.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(
            format="%(asctime)s %(levelname)-8s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            level=logging.DEBUG,
        )
    else:
        logging.basicConfig(
            format="%(asctime)s %(levelname)-8s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            level=logging.INFO,
        )

    dry_run = args.apply_to_vco
    if dry_run:
        logging.info("DRY-RUN")
    else:
        logging.info("LIVE-RUN")

    asyncio.run(async_main(args.env, args.input_csv, dry_run))
