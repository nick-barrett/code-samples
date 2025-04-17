from pydantic import ConfigDict
from typing import Literal
from veloapi.configmodules.module_base import ConfigModuleBase
from veloapi.pydantic_shared import CamelModel


class WanData(CamelModel):
    model_config = ConfigDict(extra="allow")


class ProfileWanModule(ConfigModuleBase):
    name: Literal["WAN"]
    data: WanData

    model_config = ConfigDict(extra="allow")
