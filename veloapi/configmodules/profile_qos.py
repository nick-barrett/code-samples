from pydantic import ConfigDict
from typing import Literal
from veloapi.configmodules.module_base import ConfigModuleBase
from veloapi.pydantic_shared import CamelModel


class QosData(CamelModel):
    model_config = ConfigDict(extra="allow")


class ProfileQosModule(ConfigModuleBase):
    name: Literal["QOS"]
    data: QosData

    model_config = ConfigDict(extra="allow")
