#!/usr/bin/python3

import usb
import logging
import time

log = logging.getLogger(__name__)
d = usb.core.find(idVendor=0x0fe7, idProduct=0x4001)

if d.is_kernel_driver_active(0):
    d.detach_kernel_driver(0)
#except usb.USBError as e:
#    pass # kernel driver is already detached
#    #log.warning(str(e))

d.reset()
d.set_configuration(1)
c = d.get_active_configuration()
epin = d.get_active_configuration().interfaces()[0].endpoints()[0]
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

bmRequestType=0x40 #0b01000000
bRequest=0x03
wValue=0
wIndex=0
data = b"1\r"

d.ctrl_transfer(bmRequestType, bRequest, wValue, wIndex, data)

MAX_PKT=64
reading = epin.read(MAX_PKT)
print(reading.tostring())
