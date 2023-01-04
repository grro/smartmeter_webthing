import serial
import logging
from time import sleep
from threading import Thread
from smllib import SmlStreamReader
from smllib.sml import SmlGetListResponse

class Meter:

    def __init__(self, port: str):
        self.__port = port
        self.__serial = serial.Serial (port , 9600, timeout=100)
        self.__serial.close()
        self.__current_power = 0
        self.__produced_power_total = 0
        self.__consumed_power_total = 0
        self.__listeners = set()
        Thread(target=self.__listen, daemon=True).start()

    def add_listener(self, listener):
        self.__listeners.add(listener)

    @property
    def current_power(self) -> int:
        return self.__current_power

    @property
    def produced_power_total(self) -> int:
        return self.__produced_power_total

    @property
    def consumed_power_total(self) -> int:
        return self.__consumed_power_total

    def __listen(self):
        logging.info("opening " + self.__port)
        while True:
            try:
                self.__serial.open()
                stream = SmlStreamReader()
                while True:
                    bytes = self.__serial.read(500)
                    stream.add(bytes)
                    consumed_frames = self.consume_frames(stream)
                    if consumed_frames > 0:
                        for listener in self.__listeners:
                            listener()
                    else:
                        sleep(1)
            except Exception as e:
                logging.info("error occurred processing serial data "+ str(e))
                logging.info("closing " + self.__port)
                self.__serial.close()
                sleep(1)

    def consume_frames(self, stream: SmlStreamReader) -> int:
        consumed_frames = 0
        while True:
            sml_frame = stream.get_frame()
            if sml_frame is None:
                return consumed_frames
            else:
                parsed_msgs = sml_frame.parse_frame()
                for msg in parsed_msgs:
                    if isinstance(msg.message_body, SmlGetListResponse):
                        for val in msg.message_body.val_list:
                            if str(val.obis.obis_short) == "16.7.0":
                                self.__current_power = val.get_value()
                            elif str(val.obis.obis_short) == "2.8.0":
                                self.__produced_power_total = val.get_value()
                            elif str(val.obis.obis_short) == "1.8.0":
                                self.__consumed_power_total = val.get_value()
                consumed_frames += 1


'''


meter = Meter("/dev/ttyUSB-meter")

def process():
    logging.info("aktuelle Wirkleistung: " + str(meter.current_power))
    logging.info("Zähler Einspeisung:    " + str(round(meter.produced_power_total/1000, 1)) + " kWh (" + str(meter.produced_power_total) + ")")
    logging.info("Zähler Bezug:          " + str(round(meter.consumed_power_total/1000, 1)) + " kWh (" + str(meter.consumed_power_total) + ") ")

meter.add_listener(process)


sleep(10000)
'''