import serial
import logging
from typing import List
from datetime import datetime, timedelta
from time import time
from time import sleep
from threading import Thread, Lock
from smllib import SmlStreamReader
from smllib.sml import SmlGetListResponse



class SerialReader:

    def __init__(self,
                 port,
                 data_listener,
                 error_listener,
                 close_listener,
                 max_connection_time: int,
                 read_timeout: int = 8):
        self.__lock = Lock()
        self.is_running= True
        self.__data_listener = data_listener
        self.__error_listener = error_listener
        self.__close_listener = close_listener
        self.__max_connection_time = max_connection_time
        self.__port = port
        self.sensor = serial.Serial(self.__port , 9600, timeout=read_timeout)

    def start(self):
        logging.info("opening " + self.__port)
        self.sensor.close()
        self.sensor.open()
        Thread(target=self.__listen, daemon=True).start()

    def close(self):
        with self.__lock:
            if self.is_running:
                try:
                    self.sensor.close()
                except Exception as e:
                    logging.warning("error occurred closing " + str(self.__port) + " " + str(e))
                try:
                    self.__close_listener()
                    self.is_running = False
                except Exception as e:
                    logging.warning("error occurred calling close listener" + str(e))

    def __listen(self):
        start_time = time()
        try:
            while self.is_running:
                elapsed = time() - start_time
                if elapsed < self.__max_connection_time:
                    data = self.sensor.read(100)
                    self.__data_listener(data)
                else:
                    logging.info("max connection time "+ str(self.__max_connection_time) + " sec exceeded. closing " + self.__port)
                    break
            logging.info("closing " + self.__port)
        except Exception as e:
            self.__error_listener(e)
            logging.info("closing " + self.__port + " due to error")
            sleep(3)
        finally:
            self.close()



class ReconnectingSerialReader:

    def __init__(self, port, data_listener, error_listener, reconnect_period_sec: int=15*60):
        self.is_running = True
        self.__port = port
        self.__data_listener = data_listener
        self.__error_listener = error_listener
        self.__reconnect_period_sec = reconnect_period_sec
        self.reader = SerialReader(port, data_listener, self._on_inner_stream_error, self._on_inner_stream_closed, reconnect_period_sec)

    def start(self):
        self.reader.start()

    def close(self):
        self.is_running = False
        self.reader.close()

    def _on_inner_stream_closed(self):
        if self.is_running:
            logging.info("initiate reopening of " + self.__port)
            self.reader = SerialReader(self.__port, self.__data_listener, self._on_inner_stream_error, self._on_inner_stream_closed, self.__reconnect_period_sec)
            self.reader.start()

    def _on_inner_stream_error(self, e):
        self.__error_listener(e)


class MeterValuesReader:

    def __init__(self, port, on_power_listener, on_produced_listener, on_consumed_listener, on_error_listener, reconnect_period_sec: int):
        self.is_running = True
        self.__on_power_listener = on_power_listener
        self.__on_produced_listener = on_produced_listener
        self.__on_consumed_listener = on_consumed_listener
        self.__sml_stream_reader = SmlStreamReader()
        self.reader = ReconnectingSerialReader(port, self._on_data, on_error_listener, reconnect_period_sec)

    def start(self):
        self.reader.start()

    def close(self):
        self.is_running = False
        self.reader.close()
        self.__current_power = 0

    def _on_data(self, data):
        self.__sml_stream_reader.add(data)
        while True:
            try:
                sml_frame = self.__sml_stream_reader.get_frame()
                if sml_frame is None:
                    return
                else:
                    #logging.info("frame received")
                    parsed_msgs = sml_frame.parse_frame()
                    for msg in parsed_msgs:
                        if isinstance(msg.message_body, SmlGetListResponse):
                            for val in msg.message_body.val_list:
                                if str(val.obis.obis_short) == "16.7.0":
                                    self.__on_power_listener(val.get_value())
                                elif str(val.obis.obis_short) == "2.8.0":
                                    self.__on_produced_listener(val.get_value())
                                elif str(val.obis.obis_short) == "1.8.0":
                                    self.__on_consumed_listener(val.get_value())
            except Exception as e:
                self.__sml_stream_reader.clear()
                raise e

class Meter:

    def __init__(self, port: str, reconnect_period_sec: int=15*60):
        self.__port = port
        self.__current_power = 0
        self.__produced_power_total = 0
        self.__consumed_power_total = 0
        self.__listeners = set()
        self.__current_power_samples: List[datetime] =[]
        self.__current_power_measurement_time = datetime.now() - timedelta(days=1)
        self.__last_error_date = datetime.now() - timedelta(days=365)
        self.__last_reported_power = datetime.now() - timedelta(days=365)
        self.__meter_values_reader = MeterValuesReader(port, self._on_power, self._on_produced, self._on_consumed, self._on_error, reconnect_period_sec)
        self.__meter_values_reader.start()

    def add_listener(self, listener):
        self.__listeners.add(listener)

    def __notify_listeners(self):
        try:
            for listener in self.__listeners:
                listener()
        except Exception as e:
            logging.warning("error occurred calling listener " + str(e))

    @property
    def measurement_time(self) -> datetime:
        return self.__current_power_measurement_time

    @property
    def last_error_time(self) -> datetime:
        return self.__last_error_date

    @property
    def sampling_rate(self) -> int:
        num_mesasures = len(self.__current_power_samples)
        if num_mesasures > 1:
            elapsed_sec = (self.__current_power_samples[-1] - self.__current_power_samples[0]).total_seconds()
            return round((num_mesasures / elapsed_sec) * 60)   # per  min
        else:
            return 0

    def __sample_current_power(self):
        now = datetime.now()
        self.__current_power_samples.append(now)
        for i in range(0, len(self.__current_power_samples)):
            if now > self.__current_power_samples[0] + timedelta(minutes=1):
                self.__current_power_samples.pop()
            else:
                break

    def _on_error(self, e):
        self.__last_error_date = datetime.now()
        self.__current_power_samples.clear()
        logging.info("error occurred processing serial data "+ str(e))

    def _on_power(self, current_power):
        self.__current_power = current_power
        self.__sample_current_power()
        self.__notify_listeners()
        if datetime.now() > self.__last_reported_power + timedelta(seconds=5):
            self.__last_reported_power = datetime.now()
            logging.info("current: " + str(self.__current_power) + " watt; " +
                         "sampling rate: " + str(int(self.sampling_rate)) + " per min")

    def _on_produced(self, produced_power_total):
        self.__produced_power_total = produced_power_total
        self.__notify_listeners()

    def _on_consumed(self, consumed_power_total):
        self.__consumed_power_total = consumed_power_total
        self.__notify_listeners()

    @property
    def current_power(self) -> int:
        return self.__current_power

    @property
    def produced_power_total(self) -> int:
        return self.__produced_power_total

    @property
    def consumed_power_total(self) -> int:
        return self.__consumed_power_total

