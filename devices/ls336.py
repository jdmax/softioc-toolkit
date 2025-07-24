import re
from softioc import builder
from .telnet_base import TelnetDevice, TelnetConnection


class Device(TelnetDevice):
    """Makes library of PVs needed for LS336 and provides methods connect them to the device

    Attributes:
        pvs: dict of Process Variables keyed by name
        channels: channels of device
    """

    def _create_pvs(self):
        """Create analog input PVs with calibration info"""

        mode_list = [['Off', 0], ['Closed Loop', 0], ['Zone', 0], ['Open Loop', 0]]
        range_list = [['Off', 0], ['Low', 0], ['Med', 0], ['High', 0]]

        for channel in self._skip_none_channels():  # set up PVs for each channel
            if "_TI" in channel:
                self.pvs[channel] = builder.aIn(channel, **self.sevr)
            else:
                self.pvs[channel + "_TI"] = builder.aIn(channel + "_TI", **self.sevr)
                self.pvs[channel + "_Heater"] = builder.aIn(channel + "_Heater", **self.sevr)

                self.pvs[channel + "_Manual"] = builder.aOut(channel + "_Manual", on_update_name=self.do_sets, **self.sevr)
                self.pvs[channel + "_kP"] = builder.aOut(channel + "_kP", on_update_name=self.do_sets)
                self.pvs[channel + "_kI"] = builder.aOut(channel + "_kI", on_update_name=self.do_sets)
                self.pvs[channel + "_kD"] = builder.aOut(channel + "_kD", on_update_name=self.do_sets)
                self.pvs[channel + "_SP"] = builder.aOut(channel + "_SP", on_update_name=self.do_sets, **self.sevr)

                self.pvs[channel + "_Mode"] = builder.mbbOut(channel + "_Mode", *mode_list, on_update_name=self.do_sets)
                self.pvs[channel + "_Range"] = builder.mbbOut(channel + "_Range", *range_list,
                                                              on_update_name=self.do_sets)

    def _create_connection(self):
        return DeviceConnection(
            self.settings['ip'],
            self.settings['port'],
            self.settings['timeout']
        )

    def do_sets(self, new_value, pv):
        '''If PV has changed, find the correct method to set it on the device'''
        pv_name = pv.replace(self.device_name + ':', '')  # remove device name from PV to get bare pv_name
        p = pv_name.split("_")[0]  # pv_name root
        chan = self.channels.index(p) + 1  # determine what channel we are on
        # figure out what type of PV this is, and send it to the right method
        try:
            if 'kP' in pv_name or 'kI' in pv_name or 'kD' in pv_name:  # is this a PID control record?
                dict = {}
                k_list = ['kP', 'kI', 'kD']
                for k in k_list:
                    dict[k] = self.pvs[p + "_" + k].get()  # read pvs to send to device
                values = self.t.set_pid(chan, dict['kP'], dict['kI'], dict['kD'])
                [self.pvs[p + "_" + k].set(values[i]) for i, k in enumerate(k_list)]  # set values read back
            elif 'SP' in pv_name:  # is this a setpoint?
                self.pvs[pv_name].set(self.t.set_setpoint(chan, new_value))  # set returned value
            elif 'Manual' in pv_name:  # is this a manual out?
                self.pvs[pv_name].set(self.t.set_man_heater(chan, new_value))  # set returned value
            elif 'Mode' in pv_name:
                self.pvs[pv_name].set(int(self.t.set_outmode(chan, new_value, chan, 0)))  # set returned value
            elif 'Range' in pv_name:
                self.pvs[pv_name].set(int(self.t.set_range(chan, new_value)))  # set returned value
            else:
                print('Error, control PV not categorized.')
        except OSError:
            self.reconnect()
        return

    async def do_reads(self):
        '''Match variables to methods in device driver and get reads from device'''
        try:
            temps = self.t.read_temps()
            for i, channel in enumerate(self.channels):
                if "None" in channel: continue
                if "_TI" in channel:
                    self.pvs[channel].set(temps[i])
                else:
                    self.pvs[channel + '_TI'].set(temps[i])
                    self.remove_alarm(channel+'_TI')
                    self.pvs[channel + '_Heater'].set(self.t.read_heater(i + 1))
                    pids = self.t.read_pid(i + 1)
                    self.pvs[channel + '_kP'].set(pids[0])
                    self.pvs[channel + '_kI'].set(pids[1])
                    self.pvs[channel + '_kD'].set(pids[2])
                    self.pvs[channel + '_Mode'].set(int(self.t.read_outmode(i + 1)))
                    self.pvs[channel + '_Range'].set(int(self.t.read_range(i + 1)))
                    self.pvs[channel + '_SP'].set(self.t.read_setpoint(i + 1))
                    self.pvs[channel + '_Manual'].set(self.t.read_man_heater(i + 1))
            self._handle_read_success()
            return True
        except OSError:
            self._handle_read_error()
            return False


class DeviceConnection(TelnetConnection):
    '''Handle connection to Lakeshore Model 336 via Telnet.
    '''

    def __init__(self, host, port, timeout):
        super().__init__(host, port, timeout)
        '''Define regex
        '''
        self.read_regex = re.compile(r'([+-]\d+.\d+),([+-]\d+.\d+),([+-]\d+.\d+),([+-]\d+.\d+)')
        self.pid_regex = re.compile(r'([+-]\d+.\d+),([+-]\d+.\d+),([+-]\d+.\d+)')
        self.out_regex = re.compile(r'(\d),(\d),(\d)')
        self.range_regex = re.compile(r'(\d)')
        self.setp_regex = re.compile(r'([+-]\d+.\d+)')
        # self.set_regex = re.compile('SP(\d) VALUE: (\d+.\d+)')
        # self.ok_response_regex = re.compile(b'!a!o!\s\s')

    def read_temps(self):
        '''Read temperatures for all channels.'''
        try:
            self.tn.write(bytes(f"KRDG? 0\n", 'ascii'))  # Kelvin reading
            data = self.tn.read_until(b'\n', timeout=2).decode('ascii')  # read until carriage return
            m = self.read_regex.search(data)
            values = [float(x) for x in m.groups()]
            return values

        except Exception as e:
            print(f"LS336 pid read failed on {self.host}: {e}")
            raise OSError('LS336 read')

    def set_pid(self, channel, P, I, D):
        '''Setup PID for given channel (1 or 2).'''
        try:
            self.tn.write(bytes(f"PID {channel},{P},{I},{D}\n", 'ascii'))
            self.tn.write(bytes(f"PID?\n", 'ascii'))
            data = self.tn.read_until(b'\n', timeout=2).decode('ascii')  # read until carriage return
            m = self.pid_regex.search(data)
            values = [float(x) for x in m.groups()]
            return values

        except Exception as e:
            print(f"LS336 pid set failed on {self.host}: {e}")
            raise OSError('LS336 pid set')

    def read_pid(self, channel):
        '''Read PID values for given channel (1 or 2).'''
        try:
            self.tn.write(bytes(f"PID?\n", 'ascii'))
            data = self.tn.read_until(b'\n', timeout=2).decode('ascii')  # read until carriage return
            m = self.pid_regex.search(data)
            values = [float(x) for x in m.groups()]
            return values

        except Exception as e:
            print(f"LS336 pid read failed on {self.host}: {e}")
            raise OSError('LS336 heater pid read')

    def read_heater(self, channel):
        '''Read Heater output (%) for given channel (1 or 2).'''
        try:
            self.tn.write(bytes(f"HTR? {channel}\n", 'ascii'))
            data = self.tn.read_until(b'\n', timeout=2).decode('ascii')  # read until carriage return
            m = self.setp_regex.search(data)
            values = [float(x) for x in m.groups()]
            return values[0]

        except Exception as e:
            print(f"LS336 heater read failed on {self.host}: {e}")
            raise OSError('LS336 heater read')

    def read_man_heater(self, channel):
        '''Read Manual Heater output (%) for given channel (1 or 2).'''
        try:
            self.tn.write(bytes(f"MOUT? {channel}\n", 'ascii'))
            data = self.tn.read_until(b'\n', timeout=2).decode('ascii')  # read until carriage return
            m = self.setp_regex.search(data)
            values = [float(x) for x in m.groups()]
            return values[0]

        except Exception as e:
            print(f"LS336 heater manual read failed on {self.host}: {e}")
            raise OSError('LS336 heater manual read')

    def set_man_heater(self, channel, value):
        '''Read Manual Heater output (%) for given channel (1 or 2).'''
        try:
            self.tn.write(bytes(f"MOUT {channel},{value}\n", 'ascii'))
            self.tn.write(bytes(f"MOUT? {channel}\n", 'ascii'))
            data = self.tn.read_until(b'\n', timeout=2).decode('ascii')  # read until carriage return
            m = self.setp_regex.search(data)
            values = [float(x) for x in m.groups()]
            return values[0]

        except Exception as e:
            print(f"LS336 heater manual set  failed on {self.host}: {e}")
            raise OSError('LS336 heater manual set')

    def set_outmode(self, channel, mode, in_channel, powerup_on):
        '''Setup output and readback.
        Arguments:
            channel: out put channel (1 to 4)
            mode: 0=Off, 1=Closed Loop
            in_channel: input channel for control 0=None, 1=A to 4=D
            powerup_on: Output should remain on after power cycle? 1 is yes, 0 no.
        '''
        try:
            self.tn.write(bytes(f"OUTMODE {channel},{mode},{in_channel},{powerup_on}\n", 'ascii'))
            self.tn.write(bytes(f"OUTMODE? {channel}\n", 'ascii'))
            data = self.tn.read_until(b'\n', timeout=2).decode('ascii')  # read until carriage return
            m = self.out_regex.search(data)
            values = [float(x) for x in m.groups()]
            return values[0]

        except Exception as e:
            print(f"LS336 outmode set  failed on {self.host}: {e}")
            raise OSError('LS336 outmode set')

    def read_outmode(self, channel):
        '''Read output.
        Arguments:
            channel: out put channel (1 to 4)
        '''
        try:
            self.tn.write(bytes(f"OUTMODE? {channel}\n", 'ascii'))
            data = self.tn.read_until(b'\n', timeout=2).decode('ascii')  # read until carriage return
            m = self.out_regex.search(data)
            values = [float(x) for x in m.groups()]
            return values[0]

        except Exception as e:
            print(f"LS336 outmode read failed on {self.host}: {e}")
            raise OSError('LS336 outmode read')

    def set_range(self, channel, hrange):
        '''Setup output and readback. Has no effect if outmode is off.
        Arguments:
            channel: output channel (1 to 4)
            hrange: 0=off, 1=Low, 2=Med, 3=High
        '''
        try:
            self.tn.write(bytes(f"RANGE {channel},{hrange}\n", 'ascii'))
            self.tn.write(bytes(f"RANGE? {channel}\n", 'ascii'))
            data = self.tn.read_until(b'\n', timeout=2).decode('ascii')  # read until carriage return
            m = self.range_regex.search(data)
            values = [float(x) for x in m.groups()]
            return values[0]

        except Exception as e:
            print(f"LS336 range set failed on {self.host}: {e}")
            raise OSError('LS336 range set')

    def read_range(self, channel):
        '''Read range. Has no effect if outmode is off.
        Arguments:
            channel: output channel (1 to 4)
        '''
        try:
            self.tn.write(bytes(f"RANGE? {channel}\n", 'ascii'))
            data = self.tn.read_until(b'\n', timeout=2).decode('ascii')  # read until carriage return
            m = self.range_regex.search(data)
            values = [float(x) for x in m.groups()]
            return values[0]

        except Exception as e:
            print(f"LS336 range read failed on {self.host}: {e}")
            raise OSError('LS336 range read')

    def set_setpoint(self, channel, value):
        '''Setup setpoint and read back.
        Arguments:
            channel: output channel (1 to 4)
            value: setpoint in units of loop sensor
        '''
        try:
            self.tn.write(bytes(f"SETP {channel},{value}\n", 'ascii'))
            self.tn.write(bytes(f"SETP? {channel}\n", 'ascii'))
            data = self.tn.read_until(b'\n', timeout=2).decode('ascii')  # read until carriage return
            m = self.setp_regex.search(data)
            values = [float(x) for x in m.groups()]
            return values[0]

        except Exception as e:
            print(f"LS336 range set failed on {self.host}: {e}")
            raise OSError('LS336 range set')

    def read_setpoint(self, channel):
        '''Setup setpoint and read back.
        Arguments:
            channel: output channel (1 to 4)
        '''
        try:
            self.tn.write(bytes(f"SETP? {channel}\n", 'ascii'))
            data = self.tn.read_until(b'\n', timeout=2).decode('ascii')  # read until carriage return
            m = self.setp_regex.search(data)
            values = [float(x) for x in m.groups()]
            return values[0]

        except Exception as e:
            print(f"LS336 setpoint set failed on {self.host}: {e}")
            raise OSError('LS336 setpoint set')
