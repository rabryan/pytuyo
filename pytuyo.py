import usb
import logging as log
import time
import argparse

CMD_TERMINATOR = b'\r'
MAX_RESP=64 #bytes

class Pytuyo(object):
    def __init__(self, usb_dev):
        self._usb_dev = usb_dev
        self._epin = None
        
        self.data_cb = None
        self.device_info_cb = None
        self.status_cb = None

        self.setup()

    def setup(self):
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
        log.debug("Device Vendor resp: {}".format(res1))
    
    def send_cmd(self, cmd):
        if not isinstance(cmd, bytes):
            try:
                cmd = cmd.encode()
            except Exception as e:
                raise Exception('Command bust be either bytes or str')

        if cmd[-1] != CMD_TERMINATOR:
            cmd+=CMD_TERMINATOR
        
        bmRequestType=0x40 # Vendor Host-to-Device
        bRequest=0x03
        d.ctrl_transfer(bmRequestType, bRequest, 0, 0, cmd)
    
    def request_read(self):
        self.send_cmd('1')
    
    def request_device_info(self):
        self.send_cmd('V')
    
    def _process_data_resp(self, response):
        MIN_DATA_LEN=4
        if len(response) < MIN_DATA_LEN:
            log.error("Invalid data measurement resp '{}'".format(response))
            return
    
        #ignore first two characters - always "1A"
        measure_str = response[2:] 
    
        try:
            val = float(measure_str)
        except ValueError as e:
            log.error("Unable to parse measurement '{}' to float".format(measure_str))
            return
        
        log.debug("Received measure data value: {}".format(val))

        if self.data_cb: self.data_cb(val)
    
    def _process_device_info_resp(self, response):
        log.debug("Received device info msg : {}".format(response))

        if self.device_info_cb: self.device_info_cb(response)
    
    def _process_status_resp(self, response):
        log.debug("Received device status msg : {}".format(response))

        if self.status_cb: self.status_cb(response)
        
        
    def check_resp(self):
        if self._epin is None:
            raise Exception("Device not setup correcly for reading - no interrupt IN endpoint")
        try:
            resp = self._epin.read(MAX_RESP)

            if not resp or len(resp) == 0:
                return
            
            DATA_MSG='0'
            DEVICE_INFO_MSG='1'
            STATUS_MSG='9'

            resp = resp.tobytes().decode()
            cmd_c = resp[0]
            if cmd_c == DATA_MSG:
                self._process_data_resp(resp[1:])
            elif cmd_c == DEVICE_INFO_MSG:
                self._process_device_info_resp(resp[1:])
            elif cmd_c == STATUS_MSG:
                self._process_status_resp(resp[1:])
            else:
                log.error("Ignoring unexpected device resp {}".format(resp))
        except usb.USBError as e:
            if e.errno == 110:
                log.debug("USB timeout waiting for response")
                return None
            else:
                raise

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

if __name__ == '__main__':
    import sys
    import time
    log.basicConfig(level=log.INFO)
    parser = make_parser()
    args = parser.parse_args()
    
    d = usb.core.find(idVendor=0x0fe7, idProduct=0x4001)
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
        p.check_resp()
        n = n - 1
        if n == 0:
            sys.exit(0)
        time.sleep(args.read_interval)

