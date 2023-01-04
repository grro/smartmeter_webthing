ls# Configure Smart meter IR write/read head (USB)


find usb devices 
```
sudo lsusb -v | grep 'idVendor\|idProduct\|iProduct\|iSerial'

  idVendor           0x0bda Realtek Semiconductor Corp.
  idProduct          0x8152 RTL8152 Fast Ethernet Adapter
  iProduct                2 USB 10/100 LAN
  iSerial                 3 00E04C36010F
can't get debug descriptor: Resource temporarily unavailable
can't get debug descriptor: Resource temporarily unavailable
  idVendor           0x10c4 Silicon Labs
  idProduct          0xea60 CP210x UART Bridge
  iProduct                2 CP2102 USB to UART Bridge Controller
  iSerial                 3 0035
  idVendor           0x1a40 Terminus Technology Inc.
  idProduct          0x0101 Hub
  iProduct                1 USB 2.0 Hub
  iSerial                 0
can't get debug descriptor: Resource temporarily unavailable
can't get device qualifier: Resource temporarily unavailable
can't get debug descriptor: Resource temporarily unavailable
  idVendor           0x1d6b Linux Foundation
  idProduct          0x0002 2.0 root hub
  iProduct                2 DWC OTG Controller
  iSerial                 1 20980000.usb
```


Create a rules file such as /etc/udev/rules.d/99-meter.rules based on the *product* (here "CP2102 USB to UART Bridge Controller") and *serial* (here "0035 ) attribute  
```
# /etc/udev/rules.d/99-meter.rules

SUBSYSTEM=="tty", ATTRS{product}=="CP2102 USB to UART Bridge Controller", ATTRS{serial}=="0035", SYMLINK+="ttyUSB-Meter"
```

Reload udev rules without reboot
```
sudo udevadm trigger
```


