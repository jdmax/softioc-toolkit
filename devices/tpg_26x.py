# J. Maxwell 2023
import re
from softioc import builder
from .telnet_base import TelnetDevice, TelnetConnection


class Device(TelnetDevice):
    """Makes library of PVs needed for Pfeiffer TPG 261 and 262 and provides methods connect them to the device
    """

    def _create_pvs(self):
        for channel in self._skip_none_channels():
            self.pvs[channel] = builder.aIn(channel, **self.sevr)

    def _create_connection(self):
        return DeviceConnection(
            self.settings['ip'],
            self.settings['port'],
            self.settings['timeout']
        )

class DeviceConnection(TelnetConnection):
    '''Handle connection to Pfeiffer TPG 26x via serial over ethernet.
    '''

    def __init__(self, host, port, timeout):
        '''Define regex
        '''
        super().__init__(host, port, timeout)
        # self.read_regex = re.compile('([+-]\d+.\d+)')
        self.ack_regex = re.compile(b'\r\n')
        self.read_regex = re.compile(b'\d,(.+),\d,(.+)\r\n')
        self.enq = chr(5)
        self.cr = chr(13)
        self.lf = chr(10)
        self.ack = chr(6)

    def read_all(self):
        '''Read all channels, return as list'''
        try:
            # i, match, data = self.tn.expect([self.read_regex], timeout=self.timeout)
            ##print(data)
            # return [float(x) for x in match.groups()]
            self.tn.write(b'\x03')
            command = 'PRX\r\n'
            self.tn.write(bytes(command, 'ascii'))
            i, match, data = self.tn.expect([self.ack_regex], timeout=self.timeout)
            self.tn.write(b'\x05')
            i, match, data = self.tn.expect([self.read_regex], timeout=self.timeout)
            return [float(x) for x in match.groups()]

        except Exception as e:
            print(f"TPG26x read failed on {self.host}: {e}")
