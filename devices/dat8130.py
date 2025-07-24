from .modbus_base import ModbusDevice, ModbusConnection
from softioc import builder


class Device(ModbusDevice):
    """Makes library of PVs needed for the DAT8130 relays and provides methods connect them to the device

    Attributes:
        pvs: dict of Process Variables keyed by name
        channels: channels of device
        new_reads: dict of most recent reads from device to set into PVs
    """

    def __init__(self, device_name, settings):
        super().__init__(device_name, settings)

    def _create_pvs(self):
        """Create analog input PVs with calibration info"""
        for i, channel in enumerate(self.settings['channels']):  # set up PVs for each channel, calibrations are values of dict
            if "None" in channel: continue
            if i < 4:  # Digital OUT channels first
                self.pvs[channel] = builder.boolOut(channel, on_update_name=self.do_sets)
            else:  # Digital IN next
                self.pvs[channel] = builder.boolIn(channel, **self.sevr)

    def _post_connect(self):
        """After connection, read initial output values"""
        self.read_outs()

    def read_outs(self):
        "Read and set OUT PVs at the start of the IOC"
        try:  # set initial out PVs
            values = self.t.read_coils()
            for i, channel in enumerate(self.channels[:4]):  # set all
                if "None" in channel: continue
                self.pvs[self.channels[i]].set(values[i])
        except OSError:
            self.reconnect()

    def do_sets(self, new_value, pv):
        """Set DO state"""
        pv_name = pv.replace(self.device_name + ':', '')  # remove device name from PV to get bare pv_name
        num = self.channels.index(pv_name)
        try:
            values = self.t.set_coil(num, new_value)
            for i, channel in enumerate(self.channels[:4]):  # set all
                if "None" in channel: continue
                self.pvs[self.channels[i]].set(values[i])
                self.remove_alarm(channel)
            self._handle_read_success()
            return True
        except (OSError, TypeError, AttributeError) as e:
            self._handle_read_error()
            return False

    async def do_reads(self):
        '''Match variables to methods in device driver and get reads from device'''
        try:
            readings = self.t.read_inputs()
            for i, channel in enumerate(self.channels[4:9]):
                if "None" in channel: continue
                self.pvs[channel].set(readings[i])
            self._handle_read_success()
            return True
        except OSError:
            self._handle_read_error()
            return False


class DeviceConnection(ModbusConnection):
    """Handle connection to Datexel 8130.
    """

    def read_inputs(self):
        '''Read all channels.'''
        try:
            values = self.m.read_coils(504, 8)  # read all 8 channels starting at 40
            return values
        except Exception as e:
            print(f"Datexel 8130 read failed on {self.host}: {e}")
            raise OSError('8130 read')

    def read_coils(self):
        '''Read all out channels.'''
        try:
            return self.m.read_coils(488, 4)
        except Exception as e:
            print(f"Datexel 8130 read failed on {self.host}: {e}")
            raise OSError('8130 read')

    def set_coil(self, num, state):
        '''Flip channel to state. DO channels from 0 to 3'''
        try:
            self.m.write_single_coil(488 + num, state)
            return self.read_coils()
        except Exception as e:
            print(f"Datexel 8130 write failed on {self.host}: {e}")
            raise OSError('8130 write')
