from pydantic import ConfigDict
from typing import Literal
from veloapi.configmodules.module_base import ConfigModuleBase
from veloapi.pydantic_shared import CamelModel


class DeviceSettingsData(CamelModel):
    model_config = ConfigDict(extra="allow")


class ProfileDeviceSettingsModule(ConfigModuleBase):
    name: Literal["deviceSettings"]
    data: DeviceSettingsData

    model_config = ConfigDict(extra="allow")
