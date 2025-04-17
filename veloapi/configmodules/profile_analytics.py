from pydantic import ConfigDict
from typing import Literal
from veloapi.configmodules.module_base import ConfigModuleBase
from veloapi.pydantic_shared import CamelModel


class AnalyticsData(CamelModel):
    model_config = ConfigDict(extra="allow")


class ProfileAnalyticsModule(ConfigModuleBase):
    name: Literal["analyticsSettings"]
    data: AnalyticsData

    model_config = ConfigDict(extra="allow")
