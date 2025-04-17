from pydantic import ConfigDict
from typing import Literal
from veloapi.configmodules.module_base import ConfigModuleBase
from veloapi.pydantic_shared import CamelModel


class AtpData(CamelModel):
    model_config = ConfigDict(extra="allow")


class ProfileAtpModule(ConfigModuleBase):
    name: Literal["atpMetadata"]
    data: AtpData

    model_config = ConfigDict(extra="allow")
