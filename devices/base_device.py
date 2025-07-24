# devices/base_device.py
from abc import ABC, abstractmethod
from softioc import builder, alarm


class BaseDevice(ABC):
    """Base template class for all IOC devices

    Provides common functionality like PV management, connection handling,
    alarm management, and defines the interface that all devices must implement.

    Attributes:
        pvs: dict of Process Variables keyed by name
        channels: channels of device
        device_name: name prefix for PVs
        settings: device configuration dict
    """

    def __init__(self, device_name, settings):
        """Initialize base device with common attributes"""
        self.device_name = device_name
        self.settings = settings
        self.channels = settings['channels']
        self.pvs = {}
        self.t = None  # Device connection object

        # Common severity settings
        self.sevr = {'HHSV': 'MAJOR', 'HSV': 'MINOR', 'LSV': 'MINOR', 'LLSV': 'MAJOR', 'DISP': '0'}

        # Initialize device-specific PVs
        self._create_pvs()

    @abstractmethod
    def _create_pvs(self):
        """Create device-specific PVs. Must be implemented by each device."""
        pass

    @abstractmethod
    def _create_connection(self):
        """Create device-specific connection object. Must be implemented by each device."""
        pass

    def connect(self):
        """Open connection to device"""
        try:
            self.t = self._create_connection()
            self._post_connect()
        except Exception as e:
            print(f"Failed connection on {self.settings['ip']}, {e}")

    def reconnect(self):
        """Delete connection and attempt to reconnect"""
        if self.t:
            del self.t
        print("Connection failed. Attempting reconnect.")
        self.connect()

    def _post_connect(self):
        """Default post connect is to read OUT PVs if method exists"""
        if hasattr(self, 'read_outs'):
           self.read_outs()

    def do_sets(self, new_value, pv):
        """Handle PV set operations. Override in child classes if needed."""
        pass

    @abstractmethod
    async def do_reads(self):
        """Read from device and update PVs. Must be implemented by each device."""
        pass

    def set_alarm(self, channel):
        """Set alarm and severity for channel"""
        if channel in self.pvs:
            self.pvs[channel].set_alarm(severity=1, alarm=alarm.READ_ALARM)

    def remove_alarm(self, channel):
        """Remove alarm and severity for channel"""
        if channel in self.pvs:
            self.pvs[channel].set_alarm(severity=0, alarm=alarm.NO_ALARM)


    def _skip_none_channels(self, channels=None):
        """Return list of non-None channels"""
        channels = channels or self.channels
        return [ch for ch in channels if "None" not in ch]

    def _handle_read_error(self, channels=None):
        """Set alarms for all channels on read error"""
        for channel in self._skip_none_channels(channels):
            self.set_alarm(channel)
        self.reconnect()

    def _handle_read_success(self, channels=None):
        """Remove alarms for all channels on successful read"""
        for channel in self._skip_none_channels(channels):
            self.remove_alarm(channel)