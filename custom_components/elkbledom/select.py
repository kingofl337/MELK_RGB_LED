from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers import device_registry

from .elkbledom import BLEDOMInstance
from .const import DOMAIN, MIC_EFFECTS, MIC_EFFECTS_list, BRIGHTNESS_MODES, CONF_BRIGHTNESS_MODE

import logging

LOG = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    instance = hass.data[DOMAIN][config_entry.entry_id]
    entities = [
        BLEDOMEffectSelect(instance, "Effect " + config_entry.data["name"]),
        BLEDOMMicEffect(instance, "Mic Effect " + config_entry.data["name"], config_entry.entry_id),
        BLEDOMBrightnessModeSelect(instance, "Brightness Mode " + config_entry.data["name"], config_entry, config_entry.entry_id)
    ]
    if instance.model.get_motor_modes(instance.model_name):
        entities.append(
            BLEDOMMotorModeSelect(instance, "Flicker Mode " + config_entry.data["name"], config_entry.entry_id)
        )
    async_add_entities(entities)

class BLEDOMMicEffect(RestoreEntity, SelectEntity):
    """Microphone Effect selector entity"""

    def __init__(self, bledomInstance: BLEDOMInstance, attr_name: str, entry_id: str) -> None:
        self._instance = bledomInstance
        self._attr_name = attr_name
        self._attr_unique_id = self._instance.address + "_mic_effect"
        self._current_option = MIC_EFFECTS_list[0]

    @property
    def available(self):
        return self._instance.is_on != None

    @property
    def name(self) -> str:
        return self._attr_name

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return self._attr_unique_id

    @property
    def current_option(self) -> str | None:
        return self._current_option

    @property
    def options(self) -> list[str]:
        return MIC_EFFECTS_list

    @property
    def device_info(self):
        """Return device info."""
        return DeviceInfo(
            identifiers={
                (DOMAIN, self._instance.address)
            },
            name=self.name,
            connections={(device_registry.CONNECTION_NETWORK_MAC,
                          self._instance.address)},
        )

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if option in MIC_EFFECTS_list:
            effect_value = MIC_EFFECTS[option].value
            await self._instance.set_mic_effect(effect_value)
            self._current_option = option
            LOG.debug(f"Mic effect set to {option} (0x{effect_value:02x})")

    async def async_added_to_hass(self) -> None:
        """Restore previous state when entity is added to hass."""
        await super().async_added_to_hass()
        
        # Restore the last known mic effect
        if (last_state := await self.async_get_last_state()) is not None:
            if last_state.state in MIC_EFFECTS_list:
                self._current_option = last_state.state
                LOG.debug(f"Restored mic effect for {self.name}: {self._current_option}")
            else:
                LOG.debug(f"Could not restore mic effect for {self.name}, using default")


class BLEDOMBrightnessModeSelect(RestoreEntity, SelectEntity):
    """Brightness Mode selector entity"""

    def __init__(self, bledomInstance: BLEDOMInstance, attr_name: str, entry: ConfigEntry, entry_id: str) -> None:
        self._instance = bledomInstance
        self._entry = entry
        self._attr_name = attr_name
        self._attr_unique_id = self._instance.address + "_brightness_mode"
        self._current_option = entry.options.get(CONF_BRIGHTNESS_MODE, "auto")

    @property
    def available(self):
        return self._instance.is_on != None

    @property
    def name(self) -> str:
        return self._attr_name

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return self._attr_unique_id

    @property
    def current_option(self) -> str | None:
        return self._current_option

    @property
    def options(self) -> list[str]:
        return BRIGHTNESS_MODES

    @property
    def device_info(self):
        """Return device info."""
        return DeviceInfo(
            identifiers={
                (DOMAIN, self._instance.address)
            },
            name=self.name,
            connections={(device_registry.CONNECTION_NETWORK_MAC,
                          self._instance.address)},
        )

    async def async_select_option(self, option: str) -> None:
        """Change the selected brightness mode."""
        if option not in BRIGHTNESS_MODES:
            LOG.warning("Invalid brightness mode selected: %s", option)
            return

        if option == self._current_option:
            return  # Nothing to change

        LOG.info("Changing brightness mode to %s for %s", option, self._instance.address)
        self._current_option = option

        # Update HA entry options
        data = dict(self._entry.options)
        data[CONF_BRIGHTNESS_MODE] = option
        self.hass.config_entries.async_update_entry(self._entry, options=data)

        # Apply mode to instance
        await self._instance.apply_brightness_mode(option)

        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore previous state when entity is added to hass."""
        await super().async_added_to_hass()
        
        # Restore the last known brightness mode
        if (last_state := await self.async_get_last_state()) is not None:
            if last_state.state in BRIGHTNESS_MODES:
                self._current_option = last_state.state
                LOG.debug(f"Restored brightness mode for {self.name}: {self._current_option}")
            else:
                LOG.debug(f"Could not restore brightness mode for {self.name}, using default")

        # The device instance starts in "auto" on every load; apply the restored
        # (or configured) mode to it, or the selector shows a mode that is not used.
        await self._instance.apply_brightness_mode(self._current_option)



class BLEDOMMotorModeSelect(RestoreEntity, SelectEntity):
    """Motor mode selector for star projectors (e.g. swing or rotate)."""

    _attr_icon = "mdi:rotate-3d-variant"

    def __init__(self, bledomInstance: BLEDOMInstance, attr_name: str, entry_id: str) -> None:
        self._instance = bledomInstance
        self._attr_name = attr_name
        self._attr_unique_id = self._instance.address + "_motor_mode"
        self._attr_options = list(
            self._instance.model.get_motor_modes(self._instance.model_name)
        )

    @property
    def available(self):
        return self._instance.is_on != None

    @property
    def name(self) -> str:
        return self._attr_name

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return self._attr_unique_id

    @property
    def current_option(self) -> str | None:
        return self._instance._motor_mode

    @property
    def device_info(self):
        """Return device info."""
        return DeviceInfo(
            identifiers={
                (DOMAIN, self._instance.address)
            },
            name=self.name,
            connections={(device_registry.CONNECTION_NETWORK_MAC,
                          self._instance.address)},
        )

    async def async_select_option(self, option: str) -> None:
        """Change the motor mode."""
        await self._instance.set_motor_mode(option)
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore the last known motor mode (the lamp can't be queried for it)."""
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) is not None:
            if last_state.state in self._attr_options:
                self._instance._motor_mode = last_state.state


SOLID_COLOR = "Solid color"


class BLEDOMEffectSelect(SelectEntity):
    """Effect dropdown that mirrors the light entity's effect list and current effect.

    Picking an option calls light.turn_on on the device's light, so it behaves exactly like
    choosing the effect in the light's own dialog.
    """

    _attr_icon = "mdi:string-lights"
    _attr_should_poll = False

    def __init__(self, bledomInstance: BLEDOMInstance, attr_name: str) -> None:
        self._instance = bledomInstance
        self._attr_name = attr_name
        self._attr_unique_id = self._instance.address + "_effect"
        self._attr_options = [SOLID_COLOR]
        self._attr_current_option = SOLID_COLOR
        self._light_entity_id: str | None = None

    @property
    def device_info(self):
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._instance.address)},
            connections={(device_registry.CONNECTION_NETWORK_MAC, self._instance.address)},
        )

    async def async_added_to_hass(self) -> None:
        self._find_light()

    @callback
    def _find_light(self, _now=None) -> None:
        registry = entity_registry.async_get(self.hass)
        self._light_entity_id = registry.async_get_entity_id("light", DOMAIN, self._instance.address)
        if self._light_entity_id is None:
            # The light platform may not be registered yet; try again shortly
            self.async_on_remove(async_call_later(self.hass, 5, self._find_light))
            return
        self.async_on_remove(
            async_track_state_change_event(self.hass, [self._light_entity_id], self._light_changed)
        )
        self._sync(self.hass.states.get(self._light_entity_id))
        self.async_write_ha_state()

    @callback
    def _light_changed(self, event: Event) -> None:
        self._sync(event.data.get("new_state"))
        self.async_write_ha_state()

    def _sync(self, state) -> None:
        if state is None:
            return
        self._attr_options = [SOLID_COLOR, *(state.attributes.get("effect_list") or [])]
        effect = state.attributes.get("effect")
        self._attr_current_option = effect if effect in self._attr_options else SOLID_COLOR

    @property
    def available(self) -> bool:
        if self._light_entity_id is None:
            return False
        state = self.hass.states.get(self._light_entity_id)
        return state is not None and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)

    async def async_select_option(self, option: str) -> None:
        if self._light_entity_id is None:
            raise HomeAssistantError("The light for this device was not found")
        data = {"entity_id": self._light_entity_id}
        if option == SOLID_COLOR:
            state = self.hass.states.get(self._light_entity_id)
            rgb = state.attributes.get("rgb_color") if state else None
            data["rgb_color"] = list(rgb or (255, 255, 255))
        else:
            data["effect"] = option
        await self.hass.services.async_call("light", "turn_on", data, blocking=True)
