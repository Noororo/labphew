"""
=============================
Digilent WaveForms Controller
=============================

This module is made to control `Digilent WaveForms <https://store.digilentinc.com/waveforms-download-only/>`_ compatible devices.
It is developed with the `Analog Discovery 2 <https://reference.digilentinc.com/reference/instrumentation/analog-discovery-2/start>`_ but probably also works for the other devices.

It depends on `Digilent's DWF library wrapper <https://pypi.org/project/dwf/>`_ (pip install dwf) which provides a pythonic way of interacting with the WaveForms dll.
The DfwController class inherits from the Dwf class of the dwf module, meaning all functionality of Dwf is available.
In addition the input and output channels are made available internally and basic methods are added to read and write analog values.
The example code at the end shows both examples of using these basic methods and of interacting with the more complex inherited methods.

Unfortunately there's no extended documentation for the dwf module, but original functions to interact with the dll are
described in the `WaveForms SDK Reference Manual <https://s3-us-west-2.amazonaws.com/digilent/resources/instrumentation/waveforms/waveforms_sdk_rm.pdf>`_.
Using an autocompleting IDE it's possible to explore the available methods and find the documentation of the corresponding functions in the WaveForms SDK Reference Manual.

In addition to the DfwController class this module contains functions to explore which devices are connected and to close connections.

"""

import logging
import dwf

import time
import matplotlib.pyplot as plt
import numpy as np


class DfwController(dwf.Dwf):
    def __init__(self, device_number=0, config=0):
        self.logger = logging.getLogger(__name__)
        self.logger.debug("")
        super().__init__(device_number, config)

        self.logger.debug("")
        self.AnalogIn = dwf.DwfAnalogIn(self)
        self.AnalogOut = dwf.DwfAnalogOut(self)
        self.DigitalIn = dwf.DwfDigitalIn(self)
        self.DigitalOut = dwf.DwfDigitalOut(self)

        # Not sure yet what these do:
        self.AnalogIO = dwf.DwfAnalogIO(self)
        self.DigitalIO = dwf.DwfDigitalIO(self)

        # create short name references
        self.ai = self.AnalogIn
        self.ao = self.AnalogOut
        self.di = self.DigitalIn
        self.do = self.DigitalOut

        self._basic_analog_return_std = False  # will be overwritten by preset_basic_analog()
        self._read_timeout = 1  # will be overwritten by preset_basic_analog()
        self._last_ao0 = 0  # will be overwritten by write_analog()
        self._last_ao1 = 0  # will be overwritten by write_analog()
        self._time_stabilized = time.time()  # will be overwritten by write_analog()
        self.preset_basic_analog()


    def preset_basic_analog(self, n=84, freq=10000, range=50.0, return_std=False):
        """
        Apply settings for read_analog() and write_analog()
        Please note that there may be a significant overhead (delay) for reading which seems to be larger for lower
        frequencies and oddly seems to be larger for collecting a small number of points.
        The default values of averaging over 84 points at 10kHz results in 10ms per averaged datapoint.

        :param n:     number of datapoints to collect and average (default 85)
        :type n:      int
        :param freq:  analog in frequency (default 10000)
        :type freq:   int or float or None
        :param range: the voltage range for the ADC (5.0 or 50.0) (default 50.0)
        :type range:  int or float or None
        :param return_std: also returns the standard deviations (default False)
        :type return_std:  bool
        """
        self.ao.reset()
        self.ai.reset()
        self.ao.nodeFunctionSet(-1, self.ao.NODE.CARRIER, self.ao.FUNC.DC)
        self.ao.configure(-1, 3)  # apply
        self.ai.bufferSizeSet(n)
        self.ai.frequencySet(freq)
        self.ai.channelRangeSet(-1, range)
        self.ai.configure(1, 0)  # apply config to AI, but not start
        # self._read_timeout = 1.9 + self.ai.bufferSizeGet() / self.ai.frequencyGet()
        self.ao.configure(-1, 1)


    def stop_analog_out(self, channel=-1):
        """
        Basic method to stop analog output.

        :param channel: analog out channel to stop (default is -1, meaning all channels)
        :type channel: int
        """
        self.ao.configure(channel, 0)


    def write_analog(self, volt, channel=-1):
        """
        Basic method to apply voltage to analog out channels.
        In the background it also approximates the timestamp when the output will be stabilize (based on the change in voltage applied).
        To wait for that timestamp, call wait_for_stabilization()

        :param volt: voltage to apply (in Volt)
        :type vol: float
        :param channel: analog out channel to set (default is -1, meaning all channels)
        :type channel: int
        :param delay: delay (s) to wait after setting output to allow for stabilization
        :type delay: float
        """
        self.ao.nodeOffsetSet(channel, self.ao.NODE.CARRIER, volt)
        self.ao.configure(channel, 1)
        if channel == 0 or channel == -1:
            self._time_stabilized = max(self._time_stabilized, time.time()+0.013+0.005*abs(self._last_ao0-volt))
            self._last_ao0 = volt
        if channel == 0 or channel == -1:
            self._time_stabilized = max(self._time_stabilized, time.time()+0.013+0.005*abs(self._last_ao1-volt))
            self._last_ao1 = volt

    def wait_for_stabilization(self):
        """
        Waits for the output to stabilize. Note that this is calculated and approximated, not actively measured or verified.

        :return: the amount of time waited (s)
        :rtype: float
        """
        wait = self._time_stabilized - time.time()
        if wait > 0:
            time.sleep(wait)
            return wait
        return 0

    def read_analog(self):
        """
        Basic method to read voltage of analog in channels.
        See preset_basic_analog() to setup specifics for reading.
        Returns both channels.

        :return:
        :rtype: float, float [,float, float] (or None's in case of read timeout)
        """
        daq.ai.configure(0, 1)  # start acquisition
        if self.wait_for_ai_acquisition():
            return tuple([None, None])*(1+self._basic_analog_return_std)  # return the right amount of None's
        buf = daq.ai.bufferSizeGet()
        c0 = np.array(daq.ai.statusData(0, buf))
        c1 = np.array(daq.ai.statusData(1, buf))
        if self._basic_analog_return_std:
            return c0.mean(), c1.mean(), c0.std(), c1.std()
        else:
            return c0.mean(), c1.mean()


    def wait_for_ai_acquisition(self, start_timestamp=None):
        """
        Waits while ai status is busy. Uses the AI frequency and buffersize in combination with start_timestamp to
        calculate a read timeout. If no start_timestamp is supplied it uses time at moment of calling the method.
        It returns True if timeout occured and None if acquisition finished regularly.

        :param start_timestamp:
        :type start_timestamp:
        :return: True for timeout, None when nothing happened
        :rtype: True or None
        """
        if start_timestamp is None:
            start_timestamp = time.time()
        read_timeout = 1.9 + self.ai.bufferSizeGet() / self.ai.frequencyGet()
        while daq.ai.status(True) != daq.ai.STATE.DONE:
            if time.time() > start_timestamp + read_timeout:
                self.logger.error('AI read timeout occured')
                return True


def close_all():
    """Close all Digilent "WaveForms" devices"""
    dwf.FDwfDeviceCloseAll()


def enumerate_devices():
    """
    List connected devices and their possible configurations.
    Note: Use print_device_list() to easily display the result in readable form.

    :return: list of dictionaries containing information about the devices found
    :rtype: list
    """
    devices = []
    try:
        logging.getLogger(__name__).warning(dwf.FDwfGetLastErrorMsg())
        # enumerate devices
        devs = dwf.DwfEnumeration()
        ch = lambda n=0, b=0: {'ch': n, 'buf': b}

        for i, device in enumerate(devs):
            dev_dict = {'info': {}, 'configs': []}
            dev_dict['info']['SN'] = device.SN()
            dev_dict['info']['deviceName'] = device.deviceName()
            dev_dict['info']['userName'] = device.userName()
            dev_dict['dev'] = device

            if device.isOpened():
                logging.getLogger(__name__).warning(f"Can't connect to device {i} ({dev_dict['info']['SN']}), a connection is already open.\n"
                                                     "Note that the list was stored in "+__name__+".devices at the moment of import.")
                dev_dict['configs'] = "Couldn't connect to device for further information"
            else:
                dwf_ai = dwf.DwfAnalogIn(device)
                channel = dwf_ai.channelCount()
                _, hzFreq = dwf_ai.frequencyInfo()
                dev_dict['info']['maxAIfreq'] = hzFreq
                dwf_ai.close()

                n_configs = dwf.FDwfEnumConfig(i)
                for iCfg in range(0, n_configs):
                    aic = dwf.FDwfEnumConfigInfo(iCfg, dwf.DECIAnalogInChannelCount)  # 1
                    aib = dwf.FDwfEnumConfigInfo(iCfg, dwf.DECIAnalogInBufferSize)  # 7
                    aoc = dwf.FDwfEnumConfigInfo(iCfg, dwf.DECIAnalogOutChannelCount)  # 2
                    aob = dwf.FDwfEnumConfigInfo(iCfg, dwf.DECIAnalogOutBufferSize)  # 8
                    dic = dwf.FDwfEnumConfigInfo(iCfg, dwf.DECIDigitalInChannelCount)  # 4
                    dib = dwf.FDwfEnumConfigInfo(iCfg, dwf.DECIDigitalInBufferSize)  # 9
                    doc = dwf.FDwfEnumConfigInfo(iCfg, dwf.DECIDigitalOutChannelCount)  # 5
                    dob = dwf.FDwfEnumConfigInfo(iCfg, dwf.DECIDigitalOutBufferSize)  # 10
                    dev_dict['configs'].append({'ai': ch(aic, aib), 'ao': ch(aoc, aob), 'di': ch(dic, dib), 'do': ch(doc, dob)})
                dwf_ai.close()
            devices.append(dev_dict)
    except:
        from sys import exc_info
        logging.getLogger(__name__).warning("Exception occured while enumerating devices:\n", exc_info()[0])
    return devices


# Run enumerate_devices() once when loading the module to make the list available afterwards
devices = enumerate_devices()


def print_device_list(devices_list=None):
    """
    Prints the information in the list generated by enumerate_devices() in a readable form.
    If no argument is given it prints the list stored at time of importing the module.

    :param devices: the list generated by enumerate_devices() (or None (default) to print the list stored at import)
    :type devices: list
    """
    incomplete = False
    if devices_list is None:
        global devices
        devices_list = list(devices)
        incomplete = None
    for i, device in enumerate(devices_list):
        print("------------------------------")
        print("Device " + str(i) + " : ")
        print("\tdeviceName:\t" + device['info']['deviceName'])
        print("\tuserName:\t" + device['info']['userName'])
        print("\tSN:\t\t\t" + device['info']['SN'])
        if 'maxAIfreq' in device['info']:
            print("\tmaxAIfreq:\t" + str(device['info']['maxAIfreq']))
        if type(device['configs']) is str:
            print('\t'+device['configs'])
            if incomplete is not None:
                incomplete = True
        else:
            print('\tConfig AnalogIN   AnalogOUT  DigitalIN   DigitalOUT')
            for iCfg, conf in enumerate(device['configs']):
                print('\t{}      {} x {:<5}  {} x {:<5}  {:2} x {:<5}  {:2} x {:<5}'.format(
                    iCfg, conf['ai']['ch'], conf['ai']['buf'],
                          conf['ao']['ch'], conf['ao']['buf'],
                          conf['di']['ch'], conf['di']['buf'],
                          conf['do']['ch'], conf['do']['buf']))
    if incomplete:
        print("\nThe device list appears to be incomplete. "
              "Try "+__name__+".devices_list() without argument to print the list stored at time of import")


if __name__ == '__main__':

    # Display a list of devices and their possible configurations
    devs = enumerate_devices()
    print_device_list(devs)

    # Create object for device number 0, with config number 0
    daq = DfwController(0, 0)


    print("\nTo be able to read signals we're about to generate: connect W1 to 1+, W2 to 2+, and 1- and 2- to ground (down arrow)")

    # Example showing basic analog methods:

    # Apply settings for using basic analog methods.
    # Note that this is already automatically done at instantiation of the object so technically not required at this moment.
    # But if you've those changed settings (like we'll do in the advanced example below) it is necessary.
    daq.preset_basic_analog()

    daq.write_analog( 1.3, 0)  #  1.3V on analog out channel 0
    daq.write_analog(-0.7, 1)  # -0.7V on analog out channel 1

    daq.wait_for_stabilization()

    in0, in1 = daq.read_analog()
    print(f'\nAnalog in, channel 0 is {in0:.3f} V and channel 1 is {in1:.3f} V')

    # Note: The device reads both channels simultaneously.
    # If you only need one you can select it immediately with standard python:
    read_value = daq.read_analog()[0]


    # Example illustrating the use of (advanced) inherited methods:

    print("\nConfigure analog out channel 0")
    ch_out = 0

    print('Carrier: "sine", 0.4V, 6kz, offset 1V')
    daq.ao.nodeEnableSet(ch_out, daq.ao.NODE.CARRIER, True)
    daq.ao.nodeFunctionSet(ch_out, daq.ao.NODE.CARRIER, daq.ao.FUNC.SINE)
    daq.ao.nodeFrequencySet(ch_out, daq.ao.NODE.CARRIER, 6000.0)
    daq.ao.nodePhaseSet(ch_out, daq.ao.NODE.CARRIER, 0)
    daq.ao.nodeAmplitudeSet(ch_out, daq.ao.NODE.CARRIER, 0.4)
    daq.ao.nodeOffsetSet(ch_out, daq.ao.NODE.CARRIER, 1.0)

    print('Amplitude Modulation: "ramp up", 400Hz, 100%')
    daq.ao.nodeEnableSet(ch_out, daq.ao.NODE.AM, True)
    daq.ao.nodeFunctionSet(ch_out, daq.ao.NODE.AM, daq.ao.FUNC.RAMP_UP)
    daq.ao.nodeFrequencySet(ch_out, daq.ao.NODE.AM, 400.0)
    daq.ao.nodePhaseSet(ch_out, daq.ao.NODE.AM, 0)
    daq.ao.nodeAmplitudeSet(ch_out, daq.ao.NODE.AM, 100)

    print('Frequency Modulation: "square", 100Hz, 20%, phase 90 degrees')
    daq.ao.nodeEnableSet(ch_out, daq.ao.NODE.FM, True)
    daq.ao.nodeFunctionSet(ch_out, daq.ao.NODE.FM, daq.ao.FUNC.SQUARE)
    daq.ao.nodeFrequencySet(ch_out, daq.ao.NODE.FM, 100.0)
    daq.ao.nodePhaseSet(ch_out, daq.ao.NODE.FM, 90)
    daq.ao.nodeAmplitudeSet(ch_out, daq.ao.NODE.FM, 20)

    print("\nConfigure analog in")
    print('Sampling rate 100kHz, 1000 points (i.e. 10ms)')
    n_points = 1000
    daq.ai.frequencySet(1e5)
    print("Set range for all channels")
    daq.ai.channelRangeSet(-1, 4.0)
    daq.ai.bufferSizeSet(n_points)

    print("\nStarting output and starting acquisition")
    daq.ao.configure(ch_out, 1)
    daq.ai.configure(True, 1)
    daq.wait_for_ai_acquisition()

    print("   reading data")
    scope = daq.ai.statusData(0, n_points)

    dc = sum(scope) / len(scope)
    print("DC: " + str(dc) + "V")

    t = np.arange(daq.ai.bufferSizeGet()) / daq.ai.frequencyGet()
    plt.plot(t, scope)
    plt.show()
    plt.xlabel("time (s)")
    plt.ylabel("analog in channel 0 (V)")

    # to close the device:
    # daq.close()

    # or to close all devices:
    # close_all()
