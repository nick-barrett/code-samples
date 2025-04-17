from typing import Literal

from pydantic import ConfigDict
from veloapi.configmodules.module_base import ConfigModuleBase
from veloapi.pydantic_shared import CamelModel


class AnalyticsData(CamelModel):
    model_config = ConfigDict(extra="allow")


class EdgeAnalyticsModule(ConfigModuleBase):
    name: Literal["analyticsSettings"]
    data: AnalyticsData

    model_config = ConfigDict(extra="allow")
