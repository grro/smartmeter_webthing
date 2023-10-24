ls# Configure Smart meter IR write/read head (USB)


find serial devices 
```
 ls -l /dev/serial/by-id/*
 
lrwxrwxrwx 1 root root 13 Oct 24 21:44 /dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0051-if00-port0 -> ../../ttyUSB0
```

Here a single entry is returned which is the IR read/write head. 


