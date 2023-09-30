import serial
import logging
from datetime import datetime, timedelta
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
        self.__measurement_time = datetime.now()
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

    @property
    def measurement_time(self) -> datetime:
        return self.__measurement_time

    def __listen(self):
        while True:
            sensor = None
            try:
                logging.info("opening " + self.__port)
                sensor = serial.Serial (self.__port , 9600, timeout=100)
                sensor.close()

                sensor.open()
                stream = SmlStreamReader()

                start_time = time()
                next_report_time = 0
                last_reported_power = -1
                while True:
                    elapsed = time() - start_time
                    if elapsed > 15*60:
                        break
                    data = sensor.read(500)
                    stream.add(data)
                    num_frames = self.consume_frames(stream)
                    if num_frames > 0:
                        self.__measurement_time = datetime.now()
                        for listener in self.__listeners:
                            listener()
                    else:
                        if datetime.now() > self.__measurement_time + timedelta(minutes=1):
                            break
                        else:
                            sleep(1)
                    if elapsed >= next_report_time:
                        if self.__current_power != last_reported_power:
                            last_reported_power = self.__current_power
                            next_report_time = elapsed + 5
                            logging.info("current: " + str(self.__current_power) + " watt; " +
                                         "produced total: " + str(self.__produced_power_total) + " watt; " +
                                         "consumed total: " + str(self.__consumed_power_total) + " watt; " +
                                         "measurement time: " + self.__measurement_time.strftime("%Y-%m-%dT%H:%M:%S"))
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
