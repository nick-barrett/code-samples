# Velo API Tester

A module for testing and validating Velo API endpoints and Pydantic models.

## Installation

This module is part of the `code-samples` project. Make sure you have all the required dependencies installed:

```bash
uv pip install -e .
```

## Usage

The module can be run using the `uv` command:

```bash
uv run velo_api_tester
```

## Environment Variables

The module requires the following environment variables to be set:

- `VCO_HOST`: The hostname of your VeloCloud Orchestrator
- `ENTERPRISE_ID`: Your enterprise ID
- `API_TOKEN`: Your API token

You can set these variables in a `.env` file in the project root:

```env
VCO_HOST=your-vco-host
ENTERPRISE_ID=your-enterprise-id
API_TOKEN=your-api-token
```

## Features

The module tests the following API endpoints and validates their Pydantic models:

1. Enterprise endpoint (`enterprise/getEnterprise`)
2. Enterprise edges endpoint (`enterprise/getEnterpriseEdges`)
3. Enterprise configurations policies endpoint (`enterprise/getEnterpriseConfigurationsPolicies`)
4. Edge configuration stack endpoint (`edge/getEdgeConfigurationStack`)

Each test:
- Makes the API call
- Validates the response against the Pydantic model
- Logs the results
- Provides detailed error information if validation fails

## Logging

The module uses `loguru` for logging. By default, it logs:
- INFO level: Success messages and basic information
- DEBUG level: Detailed response data
- ERROR level: Any failures or validation errors

You can adjust the logging level by setting the `LOGURU_LEVEL` environment variable. 