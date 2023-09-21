import serial
import logging
from time import time
from time import sleep
from threading import Thread
from smllib import SmlStreamReader
from smllib.sml import SmlGetListResponse

class Meter:

    def __init__(self, port: str):
        self.__port = port
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
        while True:
            sensor = None
            try:
                logging.info("opening " + self.__port)
                sensor = serial.Serial (self.__port , 9600, timeout=100)
                sensor.close()

                sensor.open()
                stream = SmlStreamReader()

                reported_frames = 0
                start_time = time()
                next_report_time = 0
                while True:
                    elapsed = time() - start_time
                    if elapsed > 59*60:
                        break
                    data = sensor.read(500)
                    stream.add(data)
                    consumed_frames = self.consume_frames(stream)
                    if consumed_frames > 0:
                        reported_frames += 1
                        for listener in self.__listeners:
                            listener()
                        else:
                            sleep(1)
                    if elapsed >= next_report_time:
                        next_report_time = time() + 60
                        logging.info("current: " + str(self.__current_power) + " watt; " +
                                     "produced total: " + str(self.__produced_power_total) + " watt; " +
                                     "consumed total: " + str(self.__consumed_power_total) + " watt; " +
                                     "frames: " + str(reported_frames))
                        reported_frames = 0
                logging.info("closing " + self.__port + " periodically")
            except Exception as e:
                logging.info("error occurred processing serial data "+ str(e))
                logging.info("closing " + self.__port + " due to error")
                try:
                    if sensor is not None:
                        sensor.close()
                except Exception as e:
                    pass
                sleep(3)

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
