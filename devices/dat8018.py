from .modbus_base import ModbusDevice, ModbusConnection
from softioc import builder


class Device(ModbusDevice):
    """Datexel 8018 Thermocouple Reader"""

    def __init__(self, device_name, settings):
        super().__init__(device_name, settings)

    def _create_pvs(self):
        """Create temperature input PVs"""
        for channel in self._skip_none_channels():
            self.pvs[channel] = builder.aIn(channel, **self.sevr)

    def _process_reading(self, channel, raw_value):
        """Convert raw value to temperature (divide by 10)"""
        return raw_value / 10
