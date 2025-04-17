"""
Velo API Tester - A module for testing and validating Velo API endpoints and Pydantic models.
"""

# Standard library imports
import asyncio
import os

# Third-party imports
from aiohttp import ClientSession
from dotenv import load_dotenv
from loguru import logger

# Local imports
from veloapi.apiv2 import (
    get_edge_configuration_stack,
    get_enterprise,
    get_enterprise_configurations_policies,
    get_enterprise_edges,
)
from veloapi.models import CommonData


async def test_enterprise_endpoint(c: CommonData) -> None:
    """Test the enterprise endpoint and validate the response model."""
    try:
        enterprise = await get_enterprise(c)
        logger.info(f"Successfully retrieved enterprise: {enterprise.name}")
        logger.debug(f"Enterprise details: {enterprise.model_dump_json(indent=2)}")
    except Exception as e:
        logger.error(f"Failed to get enterprise: {e}")
        raise


async def test_enterprise_edges_endpoint(c: CommonData) -> None:
    """Test the enterprise edges endpoint and validate the response model."""
    try:
        edges = await get_enterprise_edges(c)
        logger.info(f"Successfully retrieved {len(edges)} edges")
        for edge in edges:
            logger.debug(f"Edge details: {edge.model_dump_json(indent=2)}")
    except Exception as e:
        logger.error(f"Failed to get enterprise edges: {e}")
        raise


async def test_enterprise_configurations_policies_endpoint(c: CommonData) -> None:
    """Test the enterprise configurations policies endpoint and validate the response model."""
    try:
        policies = await get_enterprise_configurations_policies(c)
        logger.info(f"Successfully retrieved {len(policies)} configuration policies")
        for policy in policies:
            logger.debug(f"Policy details: {policy.model_dump_json(indent=2)}")
    except Exception as e:
        logger.error(f"Failed to get enterprise configuration policies: {e}")
        raise


async def test_edge_configuration_stack_endpoint(c: CommonData, edge_id: int) -> None:
    """Test the edge configuration stack endpoint and validate the response model."""
    try:
        stack = await get_edge_configuration_stack(c, edge_id)
        logger.info(f"Successfully retrieved configuration stack for edge {edge_id}")
        logger.debug(f"Stack details: {stack.model_dump_json(indent=2)}")
    except Exception as e:
        logger.error(f"Failed to get edge configuration stack: {e}")
        raise


async def run_all_tests(c: CommonData) -> None:
    """Run all API tests in sequence."""
    logger.info("Starting Velo API tests...")

    # Test enterprise endpoint
    await test_enterprise_endpoint(c)

    # Test enterprise edges endpoint
    await test_enterprise_edges_endpoint(c)

    # Test enterprise configurations policies endpoint
    await test_enterprise_configurations_policies_endpoint(c)

    # Get an edge ID to test the configuration stack
    edges = await get_enterprise_edges(c)
    if edges:
        edge_id = edges[0].id
        await test_edge_configuration_stack_endpoint(c, edge_id)
    else:
        logger.warning("No edges found to test configuration stack endpoint")

    logger.info("All tests completed successfully!")


def main() -> None:
    """Main entry point for the module."""
    # Load environment variables
    load_dotenv()

    # Get required environment variables
    vco = os.getenv("VCO_HOST")
    enterprise_id = os.getenv("ENTERPRISE_ID")
    api_token = os.getenv("API_TOKEN")

    if not all([vco, enterprise_id, api_token]):
        logger.error(
            "Missing required environment variables: VCO_HOST, ENTERPRISE_ID, API_TOKEN"
        )
        return

    async def run_tests():
        async with ClientSession() as session:
            # Create CommonData instance
            c = CommonData(
                vco=vco,
                token=api_token,
                enterprise_id=int(enterprise_id),
                session=session,
            )

            # Run all tests
            await run_all_tests(c)

    # Run the async tests
    asyncio.run(run_tests())


if __name__ == "__main__":
    main()
