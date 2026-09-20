"""Service registrations for the Robomow BLE integration."""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.components.lawn_mower.const import DOMAIN as LAWN_MOWER_DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import service
from robomow_ble_lib import Zone

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, ServiceCall

    from .lawn_mower import RobomowLawnMowerEntity

SERVICE_START_MOWING = "start_mowing"
SERVICE_SET_SCHEDULE = "set_schedule"
SERVICE_DRIVE = "drive"

ATTR_DIRECTION = "direction"
ATTR_SPEED = "speed"
ATTR_TICKS = "ticks"
ATTR_BLADES = "blades"

# Steering values used by the stock Robomow remote control.
DRIVE_DIRECTIONS = {
    "forward": -80,
    "backward": 90,
    "left": -120,
    "right": 35,
}
ATTR_STARTING_ZONE = "starting_zone"
ATTR_DURATION = "duration"

ZONE_OPTIONS = [zone.name.lower() for zone in Zone]
ZONE_VALIDATOR = vol.In(ZONE_OPTIONS)
DURATION_VALIDATOR = vol.All(vol.Coerce(int), vol.Range(min=1, max=0xFF))
CYCLES_VALIDATOR = vol.All(vol.Coerce(int), vol.Range(min=1, max=2))
OPTIONAL_TIME_VALIDATOR = vol.Any(None, cv.time)
OPTIONAL_BOOL_VALIDATOR = vol.Any(None, cv.boolean)
OPTIONAL_DURATION_VALIDATOR = vol.Any(None, DURATION_VALIDATOR)
OPTIONAL_CYCLES_VALIDATOR = vol.Any(None, CYCLES_VALIDATOR)
OPTIONAL_ZONE_VALIDATOR = vol.Any(None, ZONE_VALIDATOR)


def _build_set_schedule_schema() -> dict:
    """Build schema for set_schedule service."""
    schema: dict = {
        vol.Optional("start_time"): OPTIONAL_TIME_VALIDATOR,
        vol.Optional("end_time"): OPTIONAL_TIME_VALIDATOR,
    }

    for day in range(7):
        schema[vol.Optional(f"day_{day}_enabled")] = OPTIONAL_BOOL_VALIDATOR
        schema[vol.Optional(f"day_{day}_duration")] = OPTIONAL_DURATION_VALIDATOR
        schema[vol.Optional(f"day_{day}_cycles")] = OPTIONAL_CYCLES_VALIDATOR
        schema[vol.Optional(f"day_{day}_zone")] = OPTIONAL_ZONE_VALIDATOR

    return schema


def async_register_services(hass: HomeAssistant) -> None:
    """Register domain services."""
    if hass.services.has_service(DOMAIN, SERVICE_START_MOWING):
        return

    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_START_MOWING,
        entity_domain=LAWN_MOWER_DOMAIN,
        func=async_handle_start_mowing,
        schema=cv.make_entity_service_schema(
            {
                vol.Optional(
                    ATTR_STARTING_ZONE, default=Zone.MAIN.name.lower()
                ): ZONE_VALIDATOR,
                vol.Optional(ATTR_DURATION, default=30): DURATION_VALIDATOR,
            }
        ),
    )

    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_DRIVE,
        entity_domain=LAWN_MOWER_DOMAIN,
        func=async_handle_drive,
        schema=cv.make_entity_service_schema(
            {
                vol.Required(ATTR_DIRECTION): vol.In(sorted(DRIVE_DIRECTIONS)),
                vol.Optional(ATTR_TICKS, default=5): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=50)
                ),
                vol.Optional(ATTR_SPEED, default=100): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=100)
                ),
                vol.Optional(ATTR_BLADES, default=False): cv.boolean,
            }
        ),
    )

    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_SET_SCHEDULE,
        entity_domain=LAWN_MOWER_DOMAIN,
        func=async_handle_set_schedule,
        schema=cv.make_entity_service_schema(_build_set_schedule_schema()),
    )


def async_unregister_services_if_unused(hass: HomeAssistant) -> None:
    """Unregister domain services when there are no loaded entries left."""
    has_loaded_entries = any(
        entry.state is ConfigEntryState.LOADED
        for entry in hass.config_entries.async_entries(DOMAIN)
    )

    if not has_loaded_entries and hass.services.has_service(
        DOMAIN, SERVICE_START_MOWING
    ):
        hass.services.async_remove(DOMAIN, SERVICE_START_MOWING)

    if not has_loaded_entries and hass.services.has_service(
        DOMAIN, SERVICE_SET_SCHEDULE
    ):
        hass.services.async_remove(DOMAIN, SERVICE_SET_SCHEDULE)

    if not has_loaded_entries and hass.services.has_service(DOMAIN, SERVICE_DRIVE):
        hass.services.async_remove(DOMAIN, SERVICE_DRIVE)


async def async_handle_start_mowing(
    entity: RobomowLawnMowerEntity, call: ServiceCall
) -> None:
    """Handle start_mowing service calls."""
    await entity.async_start_mowing(
        duration_minutes=call.data.get(ATTR_DURATION),
        starting_zone=Zone[call.data[ATTR_STARTING_ZONE].upper()],
    )


async def async_handle_drive(
    entity: RobomowLawnMowerEntity, call: ServiceCall
) -> None:
    """Handle drive service calls.

    Movement is bounded: the mower stops on its own once packets stop
    arriving, so each call moves for ticks * 0.2 seconds and no longer.
    """
    await entity.coordinator.mower.async_drive(
        DRIVE_DIRECTIONS[call.data[ATTR_DIRECTION]],
        speed=call.data[ATTR_SPEED],
        ticks=call.data[ATTR_TICKS],
        blades=call.data[ATTR_BLADES],
    )


async def async_handle_set_schedule(
    entity: RobomowLawnMowerEntity, call: ServiceCall
) -> None:
    """Handle set_schedule service calls."""
    if entity.coordinator.mower.schedule is None:
        msg = "Current schedule unknown; cannot update"
        raise ValueError(msg)

    schedule = copy.deepcopy(entity.coordinator.mower.schedule)

    start_time = call.data.get("start_time")
    if start_time is not None:
        schedule.start_time = start_time

    end_time = call.data.get("end_time")
    if end_time is not None:
        schedule.end_time = end_time

    for day in range(7):
        enabled = call.data.get(f"day_{day}_enabled")
        duration = call.data.get(f"day_{day}_duration")
        cycles = call.data.get(f"day_{day}_cycles")
        zone = call.data.get(f"day_{day}_zone")

        if enabled is not None:
            schedule.day[day].enabled = enabled
        if duration is not None:
            schedule.day[day].duration = duration
        if cycles is not None:
            schedule.day[day].cycles = cycles
        if zone is not None:
            schedule.day[day].zone = Zone[zone.upper()]

    await entity.coordinator.mower.async_set_schedule(schedule)
