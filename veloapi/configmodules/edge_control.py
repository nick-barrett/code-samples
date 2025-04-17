from pydantic import ConfigDict
from typing import Literal
from veloapi.configmodules.module_base import ConfigModuleBase
from veloapi.pydantic_shared import CamelModel


class ControlData(CamelModel):
    model_config = ConfigDict(extra="allow")


class EdgeControlModule(ConfigModuleBase):
    name: Literal["controlPlane"]
    data: ControlData

    model_config = ConfigDict(extra="allow")
