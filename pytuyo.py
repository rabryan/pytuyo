#!/usr/bin/python3
# FIXME : need to handle when device is disconnected, including the ability to
# reset an interface if / when the device is reconnected

import time
import logging as _logging
from collections import deque as _deque
import usb as _usb

_log = _logging.getLogger(__name__)

CMD_TERMINATOR = b'\r'
MSG_TERMINATOR = b'\r'
READ_TIMEOUT_MS = 10
MAX_RXQUEUE_LEN=1024

DATA_MSG='0'
DEVICE_INFO_MSG='1'
STATUS_MSG='9'


class Pytuyo(object):
    _USB_CTRL_REQ_WAIT_TIME_S = .5

    _UNIT_SCALES = {'mm':(lambda x:x), 'um':(lambda x:round(x*1000))}
    _UNITS = 'mm'
    @classmethod
    def set_unit_scale(cls, scale='um'):
        cls._UNITS = scale

    def __init__(self, usb_dev):
        self._usb_dev = usb_dev
        self._epin = None
        self._rxqueue = _deque(maxlen=MAX_RXQUEUE_LEN)

        self._last_data = None
        self.data_cb = None

        self.device_info = None
        self.device_info_cb = None
        self.status_cb = None
        self._request_wait_timeout = None

        self.setup()

    def setup(self):
        d = self._usb_dev
        if d.is_kernel_driver_active(0):
            d.detach_kernel_driver(0)

        d.reset()
        d.set_configuration(1)
        c = d.get_active_configuration()
        self._epin = d.get_active_configuration().interfaces()[0].endpoints()[0]
        bmRequestType=0x40 # Vendor Host-to-Device
        bRequest=0x01
        wValue=0xA5A5
        wIndex=0
        d.ctrl_transfer(bmRequestType, bRequest, wValue, wIndex)

        bmRequestType=0xC0 # Vendor Device-to-Host
        bRequest=0x02
        wValue=0
        wIndex=0
        length=1
        res1 = d.ctrl_transfer(bmRequestType, bRequest, wValue, wIndex, length)
        _log.debug("Device Vendor resp: {}".format(res1))

    def send_cmd(self, cmd, timeout=1):
        end_time = time.time() + timeout
        while self._request_wait_timeout is not None:
            if time.time() > end_time:
                _log.warning("Cannot send mitutuyo cmd - still waiting response")
                return
            time.sleep(0.1)
            try:
                self.check_resp()
            except Exception as e:
                _log.error("Exception checking mituyou response")
                _log.error(str(e))

        if not isinstance(cmd, bytes):
            try:
                cmd = cmd.encode()
            except Exception as e:
                raise Exception('Command bust be either bytes or str')

        if cmd[-1] != CMD_TERMINATOR:
            cmd+=CMD_TERMINATOR

        bmRequestType=0x40 # Vendor Host-to-Device
        bRequest=0x03
        try:
            self._usb_dev.ctrl_transfer(bmRequestType, bRequest, 0, 0, cmd)
        except _usb.USBError as e:
            _log.error(str(e))
        else:
            self._request_wait_timeout = time.time() + Pytuyo._USB_CTRL_REQ_WAIT_TIME_S

    def request_read(self, timeout=1):
        self.send_cmd('1', timeout=timeout)

    def request_device_info(self, timeout=1):
        self.send_cmd('V', timeout=timeout)

    def get_reading(self, timeout=1):
        self._last_data = None
        self.request_read()
        time_end = timeout + time.time()
        while self._last_data is None:
            if time.time() > time_end:
                _log.error("pytuyo timeout waiting for reading")
                return None
            self.check_resp()
            time.sleep(0.05)
        return self._last_data

    def get_device_info(self, timeout=1):
        if self.device_info is not None:
            return self.device_info
        self.request_device_info()
        time_end = timeout + time.time()
        while self.device_info is None:
            if time.time() > time_end:
                _log.error("Timeout error waiting for reading")
                return None
            self.check_resp()
            time.sleep(0.05)
        return self.device_info

    def _process_data_resp(self, response):
        MIN_DATA_LEN=4
        if len(response) < MIN_DATA_LEN:
            _log.error("Invalid data measurement resp '{}'".format(response))
            return

        #ignore first two characters - always "1A"
        measure_str = response[2:]

        try:
            val = float(measure_str)
        except ValueError as e:
            _log.error("Unable to parse measurement '{}' to float".format(measure_str))
            return

        _log.debug("Received measure data value: {}".format(val))
        measure = self._UNIT_SCALES[self._UNITS](val)

        self._last_data = measure
        if self.data_cb:
            self.data_cb(measure)

    def _process_device_info_resp(self, response):
        _log.debug("Received device info msg : {}".format(response))

        self.device_info = response
        if self.device_info_cb:
            self.device_info_cb(response)

    def _process_status_resp(self, response):
        _log.debug("Received device status msg : {}".format(response))

        if self.status_cb:
            self.status_cb(response)

    def _rx(self):
        if self._epin is None:
            raise Exception("Device not setup correctly for reading - no interrupt IN endpoint")
        try:
            max_rx = self._epin.wMaxPacketSize
            resp = self._epin.read(max_rx, READ_TIMEOUT_MS)
        except _usb.USBError as e:
            if e.errno == 110:
                _log.debug("USB timeout waiting for response")
                return
            elif e.errno == 19:
                _log.debug("USB no-device error / disconnected")
                return
            else:
                raise
        except _usb.core.USBError as e:
            if e.errno == 110:
                _log.debug("USB timeout waiting for response")
                return
            elif e.errno == 19:
                _log.debug("USB no-device error / disconnected")
                return
            else:
                raise
        if not resp or len(resp) == 0:
            return
        self._rxqueue.extend(resp)

    def check_resp(self):
        try:
            self._rx()
        except Exception as e:
            _log.error("Exception checking mituyou response")
            _log.error(str(e))
            return

        if len(self._rxqueue) == 0:
            eor_idx = -1
        else:
            rxdata = bytes(self._rxqueue)
            eor_idx = rxdata.find(MSG_TERMINATOR)
        if eor_idx == -1:
            """ message terminator not received yet"""
            if self._request_wait_timeout is not None and time.time() > self._request_wait_timeout:
                _log.error("Timeout error waiting for a response")
                self._request_wait_timeout = None
            return

        resp = rxdata[:eor_idx]
        self._rxqueue.clear()

        if len(rxdata) >= eor_idx:
            """ add back any data that will not be processed"""
            remainder = resp[eor_idx+1:]
            self._rxqueue.extend(remainder)

        self._request_wait_timeout = None

        resp = resp.decode()
        msg_c = resp[0]
        if msg_c == DATA_MSG:
            self._process_data_resp(resp[1:])
        elif msg_c == DEVICE_INFO_MSG:
            self._process_device_info_resp(resp[1:])
        elif msg_c == STATUS_MSG:
            self._process_status_resp(resp[1:])
        else:
            _log.error("Ignoring unexpected device resp {}".format(resp))
        return resp



if __name__ == '__main__':
    import sys
    import time
    import argparse


    def make_parser():
        """ create the argument parser """
        parser = argparse.ArgumentParser(description="Interact with Mitutoyo USB-ITN with pyusb")

        parser.add_argument('-i', '--request-device-info', type=bool, default=True,
                help='request device info')
        parser.add_argument('-n', '--read-count', type=int, default=1,
                help='Read count. -1 for inf')
        parser.add_argument('-t', '--read-interval', type=float, default=1,
                help='Read interval in seconds')

        return parser

    _logging.basicConfig(level=_logging.INFO)
    parser = make_parser()
    args = parser.parse_args()

    d = _usb.core.find(idVendor=0x0fe7, idProduct=0x4001)
    if d is None:
        print("Could not find USB-ITN (idVendor=0x0fe7, idProduct=0x4001)")
        sys.exit(1)

    p = Pytuyo(d)

    p.data_cb = lambda v: print("M:{}".format(v))
    p.device_info_cb = lambda v: print("Device Info: {}".format(v))
    p.status_cb = lambda v: print("Device Status: {}".format(v))

    if args.request_device_info:
        p.request_device_info()
        p.check_resp()

    n = args.read_count

    while True:
        p.request_read()
        while not p.check_resp():
            pass

        n = n - 1
        if n == 0:
            sys.exit(0)
        time.sleep(args.read_interval)
