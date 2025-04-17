import asyncio
from enum import Enum
import textwrap

from aiohttp import ClientSession

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from mcp.shared.exceptions import McpError

from veloapi.apiv2 import (
    get_enterprise,
    get_enterprise_configurations_policies,
    get_enterprise_edges,
)
from veloapi.models import CommonData
from veloapi.util import read_env


class VeloTools(str, Enum):
    GET_ENTERPRISE_DETAILS = "get_enterprise_details"
    GET_EDGES = "get_edges"
    GET_ENTERPRISE_CONFIGURATIONS = "get_enterprise_configurations"


tool_descriptions = {
    VeloTools.GET_ENTERPRISE_DETAILS: textwrap.dedent(
        """\
        Retrieve details about the Velocloud enterprise.

        Returns a JSON object containing information such as the ID,
        created date, gateway pool ID, alerts enabled status,
        PKI mode, name, logical ID, and other relevant information.

        When to use this tool:
        - When you need to fetch the details of the enterprise.
        - Fetching enterprise ID or enterprise logical ID (UUID) of the current enterprise.
        """
    ),
    VeloTools.GET_EDGES: textwrap.dedent(
        """\
        Retrieve the list of edges in the Velocloud enterprise. Edges are entities inside
        a Velocloud enterprise.

        Returns a list of JSON objects, each representing an edge with its ID,
        logical ID, name, status, software versions, and other relevant information.

        When to use this tool:
        - When you need to fetch the list of edges in the enterprise.
        - When you need to check the status or software version of edges.
        """
    ),
    VeloTools.GET_ENTERPRISE_CONFIGURATIONS: textwrap.dedent(
        """\
        Retrieve the list of configuration profiles in the Velocloud enterprise. Configuration
        profiles are used as templates for edges. They contain general settings which apply to multiple edges.

        Returns a list of JSON objects, each representing a configuration profile
        with its ID, name, description, and other relevant information. 

        When to use this tool:
        - When you need to fetch the list of configuration profiles in the enterprise.
        """
    ),
}


async def async_main():
    async with ClientSession() as session:
        common = CommonData(
            read_env("VCO"), read_env("VCO_TOKEN"), int(read_env("ENT_ID")), session
        )

        server = Server("Velo MCP")

        @server.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                Tool(
                    name=VeloTools.GET_ENTERPRISE_DETAILS.value,
                    description=tool_descriptions[VeloTools.GET_ENTERPRISE_DETAILS],
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                ),
                Tool(
                    name=VeloTools.GET_EDGES.value,
                    description=tool_descriptions[VeloTools.GET_EDGES],
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                ),
                Tool(
                    name=VeloTools.GET_ENTERPRISE_CONFIGURATIONS.value,
                    description=tool_descriptions[
                        VeloTools.GET_ENTERPRISE_CONFIGURATIONS
                    ],
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                ),
            ]

        @server.call_tool()
        async def call_tool(name: str, arguments: dict) -> TextContent:
            server.request_context.session.send_log_message(
                level="info", data=f"Tool called: {name}"
            )
            try:
                match name:
                    case VeloTools.GET_ENTERPRISE_DETAILS.value:
                        res = await get_enterprise(common)

                        return [
                            TextContent(type="text", text=res.model_dump_json(indent=2))
                        ]
                    case VeloTools.GET_EDGES.value:
                        res = await get_enterprise_edges(common)

                        return [
                            TextContent(type="text", text=e.model_dump_json(indent=2))
                            for e in res
                        ]
                    case VeloTools.GET_ENTERPRISE_CONFIGURATIONS.value:
                        res = await get_enterprise_configurations_policies(common)

                        return [
                            TextContent(
                                type="text",
                                text=config_profile.model_dump_json(indent=2),
                            )
                            for config_profile in res
                        ]
                    case _:
                        raise McpError(f"Unknown tool name: {name}")
            except McpError as e:
                raise e

        options = server.create_initialization_options()
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, options)


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
