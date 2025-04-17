from datetime import datetime
import enum
from typing import Annotated, Any, Literal

from humps import camelize
from pydantic import BaseModel, BeforeValidator, ConfigDict, PlainSerializer


class NotProvidedSentinel(enum.Enum):
    NOT_PROVIDED = object()


type NotProvidedType = Literal[NotProvidedSentinel.NOT_PROVIDED]
NotProvided = NotProvidedSentinel.NOT_PROVIDED

EnterpriseObjectType = Literal[
    "NETWORK_SEGMENT", "NETWORK_SERVICE", "PRIVATE_NETWORK", "PROPERTY"
]

NetworkSegmentType = Literal["REGULAR", "CDE", "PRIVATE"]


class DatetimeSentinel(enum.Enum):
    ZERODATE = object()


type ZeroDateType = Literal[DatetimeSentinel.ZERODATE]
ZeroDate = DatetimeSentinel.ZERODATE


def _is_zero_date(value: Any) -> bool:
    # this tends to match all the zero dates that VCO returns
    # may need to add more cases here
    return isinstance(value, str) and value[:4] == "0000"


def _vco_datetime_validate(
    value: Any,
) -> datetime | ZeroDateType:
    if isinstance(value, str):
        # Proper VCO datetime strings look like this:
        # 2017-01-01T00:00:00.000Z

        if _is_zero_date(value):
            return ZeroDate

        return datetime.fromisoformat(value)

    if isinstance(value, (int, float)):
        # ms since epoch
        return datetime.fromtimestamp(value / 1000.0)

    raise ValueError("Invalid datetime format")


def _vco_datetime_serialize(value: datetime | ZeroDateType) -> int | None:
    # Convert datetime to milliseconds since epoch
    if isinstance(value, datetime):
        return int(value.timestamp() * 1000.0)

    return None


type VcoDatetime = Annotated[
    datetime | ZeroDateType,
    PlainSerializer(_vco_datetime_serialize, when_used="json"),
    BeforeValidator(_vco_datetime_validate),
]
"""Convert VCO datetimes into datetime objects.
Pydantic's default validator fails on some of the times that the VCO provides."""

type OptVcoDatetime = VcoDatetime | None

type VcoVersion = Annotated[int, BeforeValidator(int)]
"""Convert VCO version string into an integer."""


def _to_camel(s: str) -> str:
    return camelize(s)


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=_to_camel, extra="allow")
