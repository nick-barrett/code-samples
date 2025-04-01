import json
from typing import Any
from bs4 import BeautifulSoup
from pyinvindex.invindex import InvertedIndex
import asyncio
import aiohttp


def flatten_docs(data: list[dict[str, Any]], base_path: str) -> list[tuple[str, str]]:
    result = [(item["title"], base_path + item["link"]) for item in data]

    for item in data:
        if (
            (children := item.get("children", []))
            and isinstance(children, list)
            and len(children) > 0
        ):
            result.extend(flatten_docs(children, base_path))

    return result


async def download_docs(client: aiohttp.ClientSession):
    inv_index = InvertedIndex()

    # Dictionary to store document titles and links
    docs: dict[int, tuple[str, str]] = {}

    docs_json_index = "https://techdocs.broadcom.com/bin/broadcom/techdocs2/TOCServlet?basePath=%2Fcontent%2Fbroadcom%2Ftechdocs%2Fus%2Fen%2Fvmware-sde%2Fvelocloud-sase%2Fvmware-velocloud-sd-wan%2F6-1"

    async with client.get(docs_json_index) as response:
        json_data = await response.json()
        base_path = "https://techdocs.broadcom.com"
        all_docs = flatten_docs(json_data, base_path)

    total_docs = len(all_docs)
    print(f"Found {total_docs} documents to index.")

    for doc_id, (title, link) in enumerate(all_docs):
        async with client.get(link) as resp:
            if resp.status != 200:
                print(f"Failed to fetch {link}: {resp.status}")
                continue

            docs[doc_id] = (title, link)
            soup = BeautifulSoup(await resp.text(), "html.parser")
            content = soup.select_one("div.topic")
            if content:
                text = content.get_text()
                inv_index.add_document(doc_id, text)
            else:
                print(f"No content found for {link}")
        
        print(f"Indexed {doc_id + 1}/{total_docs} documents: {title}")

    # Save the index to a file
    with open("velocloud_docs_index.json", "w") as f:
        output_data = {
            "inv_index": inv_index.to_dict(),
            "docs": docs
        }
        json.dump(output_data, f, indent=4)

async def main(client: aiohttp.ClientSession):
    inv_index = InvertedIndex()
    # Dictionary to store document titles and links
    docs: dict[int, tuple[str, str]] = {}

    with open("velocloud_docs_index.json", "r") as f:
        data = json.load(f)
        inv_index.load_dict(data["inv_index"])
        docs = data["docs"]

    sample_searches = [
        "VNF",
        "ZScaler integration",
        "user roles",
        "syslog"
    ]

    for search in sample_searches:
        print("Searching for {}...".format(search))
        for res in inv_index.search_index(search)[:3]:
            doc_id, _ = res
            doc_title, doc_link = docs[doc_id]
            print(f"Title: {doc_title}")
            print(f"  ID: {doc_id}")
            print(f"  Link: {doc_link}")


if __name__ == "__main__":
    async def main_wrap():
        async with aiohttp.ClientSession() as client:
            await main(client)

    asyncio.run(main_wrap())
