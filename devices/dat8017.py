from .modbus_base import ModbusDevice, ModbusConnection
from softioc import builder


class Device(ModbusDevice):
    """Datexel 8017 ADC (4-20mA or Voltage)"""

    def __init__(self, device_name, settings):
        self.calibs = {}
        super().__init__(device_name, settings)

    def _create_pvs(self):
        """Create analog input PVs with calibration info"""
        for channel in self._skip_none_channels():
            self.calibs[channel] = self.settings['calibration'][channel]
            self.pvs[channel] = builder.aIn(channel, **self.sevr)

    def _process_reading(self, channel, raw_value):
        """Apply calibration conversion"""
        if isinstance(self.calibs[channel], int):
            # Convert from 4-20 mA to pressure using max range calibration
            return (raw_value / 1000 - 4) * (self.calibs[channel]) / 16
        else:
            return raw_value