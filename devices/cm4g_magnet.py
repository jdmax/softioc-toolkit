import re
from softioc import builder
from .telnet_base import TelnetDevice, TelnetConnection


class Device(TelnetDevice):
    """Cryomagnetics Model 4g power supply"""

    def __init__(self, device_name, settings):
        self.sweep_choice = ['UP', 'DOWN', 'PAUSE', 'ZERO', 'UP FAST', 'DOWN FAST', 'ZERO FAST']
        super().__init__(device_name, settings)

    def _create_pvs(self):
        """Create magnet-specific PVs for each channel"""
        for channel in self._skip_none_channels():
            # Read-only PVs
            self.pvs[channel + "_VI"] = builder.aIn(channel + "_VI", **self.sevr)  # Voltage
            self.pvs[channel + "_Coil_CI"] = builder.aIn(channel + "_Coil_CI", **self.sevr)  # Current
            self.pvs[channel + "_Lead_CI"] = builder.aIn(channel + "_Lead_CI", **self.sevr)  # Current

            # Control PVs
            self.pvs[channel + "_ULIM"] = builder.aOut(channel + "_ULIM", on_update_name=self.do_sets, **self.sevr)
            self.pvs[channel + "_LLIM"] = builder.aOut(channel + "_LLIM", on_update_name=self.do_sets, **self.sevr)
            self.pvs[channel + "_Sweep"] = builder.mbbOut(channel + "_Sweep", *self.sweep_choice,
                                                          on_update_name=self.do_sets)
            self.pvs[channel + "_Heater"] = builder.boolOut(channel + "_Heater", on_update_name=self.do_sets)

    def _create_connection(self):
        return DeviceConnection(
            self.settings['ip'],
            self.settings['port'],
            self.settings['timeout']
        )

    def _post_connect(self):
        """Set remote mode and read initial output values"""
        self.t.set_remote(True)
        self.read_outs()

    def read_outs(self):
        """Read and set OUT PVs at the start of the IOC"""
        for pv_name in self._skip_none_channels():
            try:
                self.pvs[pv_name + '_ULIM'].set(self.t.read_ulim())
                self.pvs[pv_name + '_LLIM'].set(self.t.read_llim())
                self.pvs[pv_name + '_Sweep'].set(self.t.read_sweep())
                self.pvs[pv_name + '_Heater'].set(self.t.read_heater())
            except OSError:
                print("Read out error on", pv_name)
                self.reconnect()

    def do_sets(self, new_value, pv):
        """Set PV values to device"""
        pv_name = pv.replace(self.device_name + ':', '')  # remove device name
        p = pv_name.split("_")[0]  # pv_name root

        try:
            if '_ULIM' in pv_name:
                value = self.t.set_ulim(self.pvs[p + '_ULIM'].get())
                self.pvs[pv_name].set(float(value))
            elif '_LLIM' in pv_name:
                value = self.t.set_llim(self.pvs[p + '_LLIM'].get())
                self.pvs[pv_name].set(float(value))
            elif '_Sweep' in pv_name:
                value = self.t.set_sweep(self.pvs[p + '_Sweep'].get())
                # Safety check: if heater on, don't allow fast sweep modes
                if value in [4, 5, 6] and self.pvs[p + '_Heater'].get():
                    value = {4: 0, 5: 1, 6: 3}[value]
                self.pvs[pv_name].set(int(value))
            elif '_Heater' in pv_name:
                value = self.t.set_heater(self.pvs[p + '_Heater'].get())
                self.pvs[pv_name].set(int(value))
            else:
                print('Error, control PV not categorized.', pv_name)
        except OSError:
            self.reconnect()

    async def do_reads(self):
        """Read magnet status and update PVs"""
        new_reads = {}
        try:
            for channel in self._skip_none_channels():
                # Read all status at once: heater, voltage, magnet current, lead current, sweep
                (new_reads[channel + '_Heater'],
                 new_reads[channel + '_VI'],
                 new_reads[channel + '_Coil_CI'],
                 new_reads[channel + '_Lead_CI'],
                 new_reads[channel + '_Sweep']) = self.t.read_status()

            # Set all PV values
            for channel, value in new_reads.items():
                self.pvs[channel].set(value)

            self._handle_read_success([ch + "_VI" for ch in self._skip_none_channels()])
            return True
        except OSError:
            self._handle_read_error([ch + "_VI" for ch in self._skip_none_channels()])
            return False


class DeviceConnection(TelnetConnection):
    """Handle connection to Cryomagnetics CS-4 via Telnet"""

    def __init__(self, host, port, timeout):
        super().__init__(host, port, timeout)
        # Compile regex patterns
        self.current_regex = re.compile(b'(-?\d+.\d+)\sA')
        self.voltage_regex = re.compile(b'(-?\d+.\d+)\sV')
        self.heater_read_regex = re.compile(b'PSHTR\?\r\n(0|1)\r\n')
        self.sweep_regex = re.compile(b'SWEEP\??\r\n(.+)\r\n')
        self.status_regex = re.compile(
            b'PSHTR\?;VMAG\?;IMAG\?;IOUT\?;SWEEP\?\r\n(\d);(-?\d+\.\d+) V;(-?\d+\.\d+) A;(-?\d+\.\d+) A;(.*)\r\n')
        self.ulim_set_regex = re.compile(b'ULIM\s(.*)\r\n')
        self.llim_set_regex = re.compile(b'LLIM\s(.*)\r\n')
        self.any_regex = re.compile(b'(.*)\r\n')

        self.sweep_choice = ['UP', 'DOWN', 'PAUSE', 'ZERO', 'UP FAST', 'DOWN FAST', 'ZERO FAST']

    def read_status(self):
        """Read status of several parameters at once"""
        try:
            command = f"PSHTR?;VMAG?;IMAG?;IOUT?;SWEEP?\n"
            self.tn.write(bytes(command, 'ascii'))
            i, match, data = self.tn.expect([self.status_regex], timeout=self.timeout)
            heat, voltage, magnet, out, sweep = match.groups()
            heater = True if b'1' in heat else False
            return heater, float(voltage), float(magnet), float(out), self.status_dec(sweep)
        except Exception as e:
            print(f"CS-4 read statuses failed on {self.host}: {e}")
            raise OSError('CS-4 read status')

    def status_dec(self, stat):
        """Convert status string to index"""
        status_map = {
            b'sweep up fast': 4, b'sweep down fast': 5, b'sweep zero fast': 6,
            b'sweep up': 0, b'sweep down': 1, b'sweep paused': 2, b'zeroing': 3
        }
        for key, value in status_map.items():
            if key in stat:
                return value
        print(f"CS-4 status decision failed on {self.host}")
        raise OSError('CS-4 status decision')

    def set_remote(self, value):
        """Put into remote mode if true, local if false"""
        try:
            command = "REMOTE\n" if value else "LOCAL\n"
            self.tn.write(bytes(command, 'ascii'))
            i, match, data = self.tn.expect([self.any_regex], timeout=self.timeout)
            return str(match.groups()[0])
        except Exception as e:
            print(f"4g set remote failed on {self.host}: {e}")
            raise OSError('4g set')

    def read_ulim(self):
        """Read upper limit"""
        try:
            self.tn.write(bytes("ULIM?\n", 'ascii'))
            i, match, data = self.tn.expect([self.current_regex], timeout=self.timeout)
            return float(match.groups()[0])
        except Exception as e:
            print(f"CS-4 read ulim failed on {self.host}: {e}")
            raise OSError('CS-4 read')

    def read_llim(self):
        """Read lower limit"""
        try:
            self.tn.write(bytes("LLIM?\n", 'ascii'))
            i, match, data = self.tn.expect([self.current_regex], timeout=self.timeout)
            return float(match.groups()[0])
        except Exception as e:
            print(f"CS-4 read llim failed on {self.host}: {e}")
            raise OSError('CS-4 read')

    def read_heater(self):
        """Read heater status"""
        try:
            self.tn.write(bytes("PSHTR?\n", 'ascii'))
            i, match, data = self.tn.expect([self.heater_read_regex], timeout=self.timeout)
            return b'1' in match.groups()[0]
        except Exception as e:
            print(f"CS-4 read heater failed on {self.host}: {e}")
            raise OSError('CS-4 read')

    def read_sweep(self):
        """Read sweep status"""
        try:
            self.tn.write(bytes("SWEEP?\n", 'ascii'))
            i, match, data = self.tn.expect([self.sweep_regex], timeout=self.timeout)
            return self.status_dec(match.groups()[0])
        except Exception as e:
            print(f"CS-4 read status failed on {self.host}: {e}")
            raise OSError('CS-4 read sweep')

    def set_ulim(self, value):
        """Set upper limit"""
        try:
            self.tn.write(bytes(f"ULIM {value}\n", 'ascii'))
            i, match, data = self.tn.expect([self.ulim_set_regex], timeout=self.timeout)
            return float(match.groups()[0])
        except Exception as e:
            print(f"CS-4 set ulim failed on {self.host}: {e}")
            raise OSError('CS-4 ulim set')

    def set_llim(self, value):
        """Set lower limit"""
        try:
            self.tn.write(bytes(f"LLIM {value}\n", 'ascii'))
            i, match, data = self.tn.expect([self.llim_set_regex], timeout=self.timeout)
            return float(match.groups()[0])
        except Exception as e:
            print(f"CS-4 set llim failed on {self.host}: {e}")
            raise OSError('CS-4 llim set')

    def set_sweep(self, index):
        """Set sweep state"""
        try:
            self.tn.write(bytes(f"SWEEP {self.sweep_choice[index]}\n", 'ascii'))
            i, match, data = self.tn.expect([self.llim_set_regex], timeout=self.timeout)
            return float(match.groups()[0])
        except Exception as e:
            print(f"CS-4 set sweep failed on {self.host}: {e}")
            raise OSError('CS-4 sweep set')

    def set_heater(self, value):
        """Set heater status"""
        state = 'on' if value else 'off'
        try:
            self.tn.write(bytes(f"PSHTR {state}\n", 'ascii'))
            i, match, data = self.tn.expect([re.compile(b'PSHTR.*\r\n')], timeout=self.timeout)
            # Read back to confirm
            self.tn.write(bytes("PSHTR?\n", 'ascii'))
            i, match, data = self.tn.expect([self.heater_read_regex], timeout=self.timeout)
            return b'1' in match.groups()[0]
        except Exception as e:
            print(f"CS-4 set heater failed on {self.host}: {e}")
            raise OSError('CS-4 heater set')