import re
from .telnet_base import TelnetDevice, TelnetConnection
from softioc import builder


class Device(TelnetDevice):
    """AMI Model 136 Level Monitor"""

    def _create_pvs(self):
        """Create level input PVs for each channel"""
        for channel in self._skip_none_channels():
            self.pvs[channel] = builder.aIn(channel, **self.sevr)

    def _create_connection(self):
        return DeviceConnection(
            self.settings['ip'],
            self.settings['port'],
            self.settings['timeout']
        )

class DeviceConnection(TelnetConnection):
    """Handle connection to AMI Model 136 via serial over ethernet"""

    def __init__(self, host, port, timeout):
        super().__init__(host, port, timeout)
        self.read_regex = re.compile(r'(\d+.\d+)')
        
        try:
            self.tn.write(bytes(f"PERCENT\n", 'ascii'))
            data = self.tn.read_until(b'\n', timeout=self.timeout).decode('ascii')
        except Exception as e:
            print(f"AMI136 PERCENT mode set failed on {self.host}: {e}")

    def read_all(self):
        """Read level from device"""
        try:
            self.tn.write(bytes(f"LEVEL\n", 'ascii'))
            data = self.tn.read_until(b'\n', timeout=self.timeout).decode('ascii')
            ms = self.read_regex.findall(data)
            values = [float(m) for m in ms]
            if not values:
                raise OSError('AMI136 read')
            return values
        except Exception as e:
            print(f"AMI136 read failed on {self.host}: {e}")
            raise OSError('AMI136 read')