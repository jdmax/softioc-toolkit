from .modbus_base import ModbusDevice, ModbusConnection
from softioc import builder


class Device(ModbusDevice):
    """Datexel 8024 Analog Output Module"""

    def _create_pvs(self):
        """Create analog output PVs"""
        for channel in self._skip_none_channels():
            self.pvs[channel] = builder.aOut(channel, on_update_name=self.do_sets, **self.sevr)

    def _post_connect(self):
        """After connection, read initial output values"""
        self.read_outs()

    async def do_reads(self):
        """ DAT8024 read implementation"""
        try:
            readings = self.t.read_all(40, 4)
            for i, channel in enumerate(self._skip_none_channels()):
                processed_value = self._process_reading(channel, readings[i])
                self.pvs[channel].set(processed_value)
            self._handle_read_success()
            return True
        except (OSError, TypeError, AttributeError) as e:
            self._handle_read_error()
            return False

    def read_outs(self):
        """Read and set OUT PVs at the start of the IOC"""
        try:
            values = self.t.read_all(40, 4)
            for i, channel in enumerate(list(self._skip_none_channels())[:4]):  # Only 4 outputs
                self.pvs[channel].set(values[i])
        except OSError:
            self.reconnect()

    def do_sets(self, new_value, pv):
        """Set analog output value"""
        pv_name = pv.replace(self.device_name + ':', '')
        num = list(self._skip_none_channels()).index(pv_name)
        try:
            self.t.set_register(40 + num, int(new_value * 1000))
            readings = self.t.read_all(40, 4)
            for i, channel in enumerate(list(self._skip_none_channels())[:4]):
                processed_value = self._process_reading(channel, readings[i])
                self.pvs[channel].set(processed_value)
        except (OSError, TypeError):
            self.reconnect()

    def _process_reading(self, channel, raw_value):
        """Convert from mV to V"""
        return raw_value / 1000
