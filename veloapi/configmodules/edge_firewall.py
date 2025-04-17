from pydantic import ConfigDict
from typing import Literal
from veloapi.configmodules.module_base import ConfigModuleBase
from veloapi.pydantic_shared import CamelModel


class FirewallData(CamelModel):
    model_config = ConfigDict(extra="allow")


class EdgeFirewallModule(ConfigModuleBase):
    name: Literal["firewall"]
    data: FirewallData

    model_config = ConfigDict(extra="allow")
