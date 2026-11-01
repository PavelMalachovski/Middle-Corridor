"""Перевод часов демо (только мок с DEMO_CONTROL=true): модели и интерфейс."""

from datetime import datetime
from typing import Literal, Protocol, Self

from pydantic import BaseModel, Field, model_validator


class DemoClockState(BaseModel):
    now: datetime  # мок-«сейчас» с учётом сдвига
    offset_hours: float
    story_start: datetime  # старт демо-истории (сбрасывается вместе с часами)
    story_ref: str  # груз демо-истории


class DemoClockAction(BaseModel):
    action: Literal["advance", "next_beat", "reset"]
    # только для advance: > 0 и не больше 30 суток — огромный сдвиг переполнил бы часы
    hours: float | None = Field(default=None, le=720)

    @model_validator(mode="after")
    def _hours_for_advance(self) -> Self:
        if self.action == "advance" and (self.hours is None or self.hours <= 0):
            raise ValueError("advance требует hours > 0")
        return self


class DemoClockControl(Protocol):
    def state(self) -> DemoClockState: ...

    def apply(self, action: DemoClockAction) -> DemoClockState: ...
