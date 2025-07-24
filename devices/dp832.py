import re
import time
from softioc import builder, alarm
from .telnet_base import TelnetDevice, TelnetConnection


class Device(TelnetDevice):
    '''Makes library of PVs needed for Rigol DP832 and provides methods connect them to the device
    '''

    def _create_pvs(self):
        """Create magnet-specific PVs for each channel"""

        for channel in self._skip_none_channels():  # set up PVs for each channel
            self.pvs[channel+"_VI"] = builder.aIn(channel+"_VI", **self.sevr)   # Voltage
            self.pvs[channel+"_CI"] = builder.aIn(channel+"_CI", **self.sevr)   # Current
            self.pvs[channel + "_CC"] = builder.aOut(channel + "_CC", on_update_name=self.do_sets, **self.sevr)
            self.pvs[channel + "_VC"] = builder.aOut(channel + "_VC", on_update_name=self.do_sets, **self.sevr)
            self.pvs[channel + "_Mode"] = builder.boolOut(channel + "_Mode", on_update_name=self.do_sets)

    def _create_connection(self):
        return DeviceConnection(
            self.settings['ip'],
            self.settings['port'],
            self.settings['timeout']
        )

    def read_outs(self):
        """Read and set OUT PVs at the start of the IOC"""
        for i, pv_name in enumerate(self.channels):
            if "None" in pv_name: continue
            try:
                values = self.t.read_sp(str(i+1))
                self.pvs[pv_name + '_VC'].set(values[0])  # set returned voltage
                self.pvs[pv_name + '_CC'].set(values[1])  # set returned current
                value = self.t.set_state(str(i+1), self.pvs[pv_name].get())
                self.pvs[pv_name + '_Mode'].set(int(value))  # set returned value
            except OSError:
                print("Read out error on", pv_name)
                self.reconnect()


    def do_sets(self, new_value, pv):
        """Set PVs values to device"""
        pv_name = pv.replace(self.device_name + ':', '')  # remove device name from PV to get bare pv_name
        p = pv_name.split("_")[0]  # pv_name root
        chan = self.channels.index(p) + 1  # determine what channel we are on
        # figure out what type of PV this is, and send it to the right method
        try:
            if 'CC' in pv_name or 'VC' in pv_name:  # is this a current set? Voltage set from settings file
                values = self.t.set(chan, self.pvs[p + '_VC'].get(), self.pvs[p + '_CC'].get())
                self.pvs[p + '_VC'].set(values[0])  # set returned voltage
                self.pvs[p + '_CC'].set(values[1])  # set returned current
            elif 'Mode' in pv_name:
                value = self.t.set_state(chan, new_value)
                self.pvs[pv_name].set(int(value))  # set returned value
            else:
                print('Error, control PV not categorized.', pv_name)
        except OSError:
            self.reconnect()
        return

    async def do_reads(self):
        '''Match variables to methods in device driver and get reads from device'''
        new_reads = {}
        try:
            for i, channel in enumerate(self.channels):
                if "None" in channel: continue
                new_reads[channel + '_VI'], new_reads[channel + '_CI'], power = self.t.read(i + 1)
                new_reads[channel + '_VC'], new_reads[channel + '_CC'] = self.t.read_sp(i + 1)
                new_reads[channel + '_Mode'] = self.t.read_state(i + 1)
            for channel, value in new_reads.items():
                self.pvs[channel].set(value)

            self._handle_read_success()
            return True
        except OSError:
            self._handle_read_error()
            return False



class DeviceConnection(TelnetConnection):
    '''Handle connection to Rigol DP832 via Telnet.
    '''

    def __init__(self, host, port, timeout):
        super().__init__(host, port, timeout)

        self.read_regex = re.compile(r'CH\d:\d+V/\dA,(\d+.\d+),(\d+.\d+)')
        self.read_sp_regex = re.compile(r'(\d+.\d+),(\d+.\d+),(\d+.\d+)')

    def read_sp(self, channel):
        '''Read voltage, current measured for given channel (1,2,3).'''
        try:
            command = f":APPLY? CH{channel}\n"
            self.tn.write(bytes(command, 'ascii'))   # Reading
            data = self.tn.read_until(b'\n', timeout=self.timeout).decode('ascii')  # read until carriage return
            m = self.read_regex.search(data)
            values = [float(x) for x in m.groups()]
            return values   # return voltage, current as list

        except Exception as e:
            print(f"DP832 read sp failed on {self.host}: {e},{command},{data}")
            raise OSError('DP832 read sp')

    def read(self, channel):
        '''Read voltage, current measured for given channel (1,2,3).'''
        try:
            command = f":MEASURE:ALL? CH{channel}\n"
            self.tn.write(bytes(command, 'ascii'))   # Reading
            data = self.tn.read_until(b'\n', timeout=self.timeout).decode('ascii')  # read until carriage return
            m = self.read_sp_regex.search(data)
            values = [float(x) for x in m.groups()]
            return values   # return voltage, current as list

        except Exception as e:
            print(f"DP832 read failed on {self.host}: {e}, {command},{data}")
            raise OSError('DP832 read')

    def set(self, channel, voltage, current):
        '''Set current and voltage for given channel'''
        try:
            self.tn.write(bytes(f":APPLY CH{channel},{voltage},{current}\n", 'ascii'))
            time.sleep(0.2)
            return self.read_sp(channel)   # return voltage, current as list

        except Exception as e:
            print(f"DP832 set failed on {self.host}: {e}")
            raise OSError('DP832 set')

    def read_state(self, channel):
        '''Read output state for given channel.
        Arguments:
            channel: out put channel (1 to 4)
        '''
        try:
            self.tn.write(bytes(f"OUTPUT? CH{channel}\n", 'ascii'))
            data = self.tn.read_until(b'\n', timeout=self.timeout).decode('ascii')  # read until carriage return
            state = True if 'ON' in data else False
            return state

        except Exception as e:
            print(f"DP832 outmode read failed on {self.host}: {e}")
            raise OSError('DP832 outmode read')

    def set_state(self, channel, state):
        '''Setup output state on (true) or off (false).
        Arguments:
            channel: out put channel (1 to 4)
            state: False=Off, True=On
        '''
        out = 'ON' if state else 'OFF'
        try:
            self.tn.write(bytes(f":OUTPUT CH{channel},{out}\n", 'ascii'))
            time.sleep(0.2)
            return self.read_state(channel)
        except Exception as e:
            print(f"DP832 out set failed on {self.host}: {e}")
            raise OSError('DP832 out set')
