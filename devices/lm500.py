import re
from softioc import builder
from .telnet_base import TelnetDevice, TelnetConnection


class Device(TelnetDevice):
    """Makes library of PVs needed for LM500 and provides methods connect them to the device

    Attributes:
        pvs: dict of Process Variables keyed by name
        channels: channels of device
    """

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
    """Handle connection to LM500 level probe"""

    def __init__(self, host, port, timeout):
        super().__init__(host, port, timeout)
        self.read_regex = re.compile(b'.+\r\n(-?\d*\.\d)\s')

    def read_all(self):
        '''Read level.'''
        try:
            self.tn.write(bytes(f"MEAS?\n", 'ascii'))  # 0 means it will return all channels
            i, match, data = self.tn.expect([self.read_regex], timeout=self.timeout)
            return [float(x) for x in match.groups()]

        except Exception as e:
            print(f"LM-500 read failed on {self.host}: {e}, {data}")
            raise OSError('LM-500 read')
