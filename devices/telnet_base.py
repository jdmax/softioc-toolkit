import telnetlib
from .base_device import BaseDevice


class TelnetDevice(BaseDevice):
    """Base class for Telnet devices"""

    async def do_reads(self):
        """Generic telnet read implementation"""
        try:
            readings = self.t.read_all()
            for i, channel in enumerate(self.channels):
                if "None" in channel: continue
                processed_value = self._process_reading(channel, readings[i])
                self.pvs[channel].set(processed_value)
            self._handle_read_success()
            return True
        except OSError:
            self._handle_read_error()
            return False

    def _process_reading(self, channel, raw_value):
        """Process raw reading value. Override in child classes if needed."""
        return raw_value


class TelnetConnection:
    """Generic Telnet connection handler"""

    def __init__(self, host, port, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout

        try:
            self.tn = telnetlib.Telnet(self.host, port=self.port, timeout=self.timeout)
        except Exception as e:
            print(f"Telnet connection failed on {self.host}: {e}")
