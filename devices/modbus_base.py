from pyModbusTCP.client import ModbusClient
from .base_device import BaseDevice


class ModbusDevice(BaseDevice):
    """Base class for Modbus devices (Datexel series)"""

    def __init__(self, device_name, settings):
        super().__init__(device_name, settings)

    def _create_connection(self):
        """Create Modbus connection"""
        return ModbusConnection( # set time of last successful update
            self.settings['ip'],
            self.settings['port'],
            self.settings['timeout']
        )

    async def do_reads(self):
        """Generic Modbus read implementation"""
        try:
            readings = self.t.read_all()
            for i, channel in enumerate(self._skip_none_channels()):
                processed_value = self._process_reading(channel, readings[i])
                self.pvs[channel].set(processed_value)
            self._handle_read_success()
            return True
        except (OSError, TypeError, AttributeError) as e:
            print(e)
            self._handle_read_error()
            return False

    def _process_reading(self, channel, raw_value):
        """Process raw reading value. Override in child classes if needed."""
        return raw_value


class ModbusConnection:
    """Generic Modbus connection handler"""

    def __init__(self, host, port, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout

        try:
            self.m = ModbusClient(host=self.host, port=int(self.port), unit_id=1, auto_open=True)
        except Exception as e:
            print(f"Modbus connection failed on {self.host}: {e}")

    def read_all(self, start=40, number=8):
        return self.read_registers(start, number)

    def read_registers(self, start, number):
        """Read {number} input registers starting at {start}"""
        try:
            return self.m.read_input_registers(start, number)  # Default: 8 channels starting at 40
        except Exception as e:
            print(f"Modbus read failed on {self.host}: {e}")
            raise OSError('Modbus read')

    def set_register(self, number, value):
        """Set register {number} with {value}"""
        try:
            #self.m.write_single_register(40 + num, int(value*1000))  # set as mV
            self.m.write_single_register(number, value)  # set as mV
            return True
        except Exception as e:
            print(f"Modbus set failed on {self.host}: {e}")
            raise OSError('Modbus  set')