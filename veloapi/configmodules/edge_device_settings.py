from pydantic import ConfigDict
from typing import Literal
from veloapi.configmodules.module_base import ConfigModuleBase
from veloapi.pydantic_shared import CamelModel


class DeviceSettingsData(CamelModel):
    model_config = ConfigDict(extra="allow")


class EdgeDeviceSettingsModule(ConfigModuleBase):
    name: Literal["deviceSettings"]
    data: DeviceSettingsData

    model_config = ConfigDict(extra="allow")
