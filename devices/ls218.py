import re
from softioc import builder
from .telnet_base import TelnetDevice, TelnetConnection


class Device(TelnetDevice):
    """Lakeshore 218 Temperature Monitor"""

    def _create_pvs(self):
        """Create temperature input PVs for each channel"""
        for channel in self._skip_none_channels():
            self.pvs[channel] = builder.aIn(channel, **self.sevr)

    def _create_connection(self):
        return DeviceConnection(
            self.settings['ip'],
            self.settings['port'],
            self.settings['timeout']
        )


class DeviceConnection(TelnetConnection):
    """Handle connection to Lakeshore Model 218 via serial over ethernet"""

    def __init__(self, host, port, timeout):
        super().__init__(host, port, timeout)
        self.read_regex = re.compile(r'([+-]\d+.\d+)')

    def read_all(self):
        """Read temperatures for all channels"""
        try:
            self.tn.write(bytes(f"KRDG? 0\n", 'ascii'))  # 0 means all channels
            data = self.tn.read_until(b'\n', timeout=2).decode('ascii')
            ms = self.read_regex.findall(data)
            return [float(m) for m in ms]
        except Exception as e:
            print(f"LS218 read failed on {self.host}: {e}")
            raise OSError('LS218 read')
