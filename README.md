# smart meter webthing
A webthing connector for smart meters

This project provides a smart meter [webthing API](https://webthings.io/). It provides the software to connect an [IR USB sensor](https://wiki.volkszaehler.org/hardware/controllers/ir-schreib-lesekopf-usb-ausgang)

<img src="img.png" height="350" />

The smart meter webthing package provides an http webthing endpoint that supports smart meter consumption values over http. e.g.
```
# webthing has been started on host 192.168.0.23

curl http://192.168.0.23:7122/properties 

{
   "current_power": 389,
   "produced_power_total": 3314.7,
   "consumed_power_total": 259784.2
}
```

To install this software, you can use the [PIP](https://realpython.com/what-is-pip/) package manager as shown below
```
sudo pip install smartmeter_webthing
```

After installation, you can start the webthing http endpoint in your Python code or from the command line by typing
```
sudo smartmeter --command listen --port 7122 --sport /dev/ttyUSB-meter 
```
Here the webthing API will use the local port 7122. Additionally, the device address of the IR sensor must be set. To configure the device address, see [setup device](configure.md).

As an alternative to the *list* command, you can also use the *register* command to register and start the webthing service as a systemd device.
This way, the webthing service is started automatically at boot time. Starting the server manually with the *listen* command, as shown above, is no longer necessary.

```
sudo smartmeter --command register --port 7122 --sport /dev/ttyUSB-meter 
```  