# smart meter webthing
A smart meter web thing connector

This project provides a smart meter [webthing API](https://webthings.io/). It provides the software to connect an [IR USB sensor](https://wiki.volkszaehler.org/hardware/controllers/ir-schreib-lesekopf-usb-ausgang)  

<img src="img.png" height="350" />

The smart meter webthing package exposes a http webthing endpoint supporting the smart meter consumption values via http. E.g.
```
# webthing has been started on host 192.168.0.23

curl http://192.168.0.23:7122/properties 

{
   "current_power": 389,
   "produced_power_total": 3314.7,
   "consumed_power_total": 259784.2
}
```

To install this software you may use [PIP](https://realpython.com/what-is-pip/) package manager such as shown below
```
sudo pip install smartmeter_webthing
```

After this installation you may start the webthing http endpoint inside your python code or via command line using
```
sudo smartmeter --command listen --port 7122 --sport /dev/ttyUSB-meter 
```
Here, the webthing API will use the local port 7122. Additionally, the device address of the IR sensor has to be set. To configure the device address refer [setup device](configure.md)  

Alternatively to the *listen* command, you can use the *register* command to register and start the webthing service as systemd unit.
By doing this, the webthing service will be started automatically on boot time. Starting the server manually using the *listen* command as shown above is no longer necessary.
```
sudo smartmeter --command register --port 7122 --sport /dev/ttyUSB-meter 
```  