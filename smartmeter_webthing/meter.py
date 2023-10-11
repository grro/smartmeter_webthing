import serial
import logging
from abc import ABC, abstractmethod
from typing import List, Final
from datetime import datetime, timedelta
from time import time
from time import sleep
from threading import Thread, RLock
from smllib import SmlStreamReader
from smllib.sml import SmlGetListResponse
from redzoo.database.simple import SimpleDB


class DataListener(ABC):

    @abstractmethod
    def on_read(self, data):
        pass

    @abstractmethod
    def on_read_error(self, e):
        pass


class LifecycleListener(ABC):

    @abstractmethod
    def on_closed(self):
        pass


class SerialReader:

    def __init__(self,
                 port: str,
                 data_listener: DataListener,
                 lifecycle_listener: LifecycleListener,
                 max_connection_time: int,
                 read_timeout: int = 8):
        self.__lock: Final = RLock()
        self.__data_listener = data_listener
        self.__lifecycle_listener = lifecycle_listener
        self.__max_connection_time = max_connection_time
        self.__port = port
        self.__read_timeout = read_timeout
        self.is_running = True
        self.sensor = serial.Serial(self.__port, 9600, timeout=read_timeout)

    def start(self):
        logging.info("sensor - opening " + self.__port)
        self.sensor.close()
        self.sensor.open()
        Thread(target=self.__listen, daemon=True).start()

    def close(self):
        with self.__lock:
            if self.is_running:
                try:
                    self.sensor.close()
                except Exception as e:
                    logging.warning("sensor - error occurred closing " + str(self.__port) + " " + str(e))
                try:
                    self.__lifecycle_listener.on_closed()
                    self.is_running = False
                except Exception as e:
                    logging.warning("sensor - error occurred calling close listener" + str(e))


    def __listen(self):
        num_consecutive_errors = 0
        start_time = time()
        try:
            while self.is_running:
                elapsed = time() - start_time
                if elapsed > self.__max_connection_time:
                    logging.info("sensor - max connection time "+ str(self.__max_connection_time) + " sec exceeded. closing " + self.__port)
                    break
                else:
                    try:
                        data = self.sensor.read(100)
                        if len(data) > 0:
                            num_consecutive_errors = 0
                            self.__data_listener.on_read(data)
                        else:
                            raise Exception("sensor - no data received within " + str(self.__read_timeout) + " sec")
                    except Exception as e:
                        num_consecutive_errors += 1
                        self.__data_listener.on_read_error(e)
                        if num_consecutive_errors >= 3:
                            raise Exception("sensor - error occurred reading data ", e)
            logging.info("sensor - closing " + self.__port)
        except Exception as e:
            logging.info("sensor - closing " + self.__port + " due to error")
            sleep(3)
        finally:
            self.close()


class ReconnectingSerialReader(LifecycleListener):

    def __init__(self, port: str, data_listener: DataListener, reconnect_period_sec: int = 15*60):
        self.is_running = True
        self.__port = port
        self.__data_listener = data_listener
        self.__reconnect_period_sec = reconnect_period_sec
        self.reader = SerialReader(port, data_listener, self, reconnect_period_sec)

    def on_closed(self):
        if self.is_running:
            self.reader = SerialReader(self.__port, self.__data_listener, self, self.__reconnect_period_sec)
            self.reader.start()

    def start(self):
        self.reader.start()

    def close(self):
        self.is_running = False
        self.reader.close()


class MeterValuesReader(DataListener):

    def __init__(self,
                 port: str,
                 on_power_listener,
                 on_produced_listener,
                 on_consumed_listener,
                 on_error_listener,
                 reconnect_period_sec: int):
        self.__on_power_listener = on_power_listener
        self.__on_produced_listener = on_produced_listener
        self.__on_consumed_listener = on_consumed_listener
        self.__on_error_listener = on_error_listener
        self.__sml_stream_reader = SmlStreamReader()
        self.reader = ReconnectingSerialReader(port, self, reconnect_period_sec)

    def start(self):
        self.reader.start()

    def close(self):
        self.reader.close()

    def on_read(self, data):
        self.__sml_stream_reader.add(data)
        for i in range(0, len(data)):   # limit loops in case of strange errors
            try:
                sml_frame = self.__sml_stream_reader.get_frame()
                if sml_frame is None:
                    return
                else:
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
                logging.warning(Exception("error occurred parsing frame", e))

    def on_read_error(self, e):
        self.__sml_stream_reader.clear()
        self.__on_error_listener(e)


class Meter:

    def __init__(self, port: str, reconnect_period_sec: int=90*60):
        self.__db = SimpleDB("meter_daily_power_values", sync_period_sec=10*60)
        self.__port = port
        self.__current_power = 0
        self.__produced_power_total = 0
        self.__consumed_power_total = 0
        self.__listeners = set()
        self.__power_measurements: List[datetime] =[]
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
    def sampling_rate(self) -> int:
        num_measurements = len(self.__power_measurements)
        if num_measurements > 1:
            elapsed_sec = (self.__power_measurements[-1] - self.__power_measurements[0]).total_seconds()
            return round((num_measurements / elapsed_sec) * 60)   # per  min
        else:
            return 0

    def __sample_current_power(self):
        now = datetime.now()
        self.__power_measurements.append(now)
        for i in range(0, len(self.__power_measurements)):
            if now > self.__power_measurements[0] + timedelta(seconds=90):
                self.__power_measurements.pop()
            else:
                break

    @property
    def measurement_time(self) -> datetime:
        return self.__current_power_measurement_time

    @property
    def last_error_time(self) -> datetime:
        return self.__last_error_date

    def _on_error(self, e):
        logging.warning("error occurred processing serial data " + str(e))
        self.__last_error_date = datetime.now()
        self.__current_power = 0
        self.__power_measurements.clear()
        self.__notify_listeners()

    def _on_power(self, current_power: int):
        self.__current_power = current_power
        self.__sample_current_power()
        self.__notify_listeners()
        self.__db.put(datetime.now().strftime("%H:%M"), current_power)
        if datetime.now() > self.__last_reported_power + timedelta(seconds=5):
            self.__last_reported_power = datetime.now()
            logging.info("current: " + str(self.__current_power) + " watt; " +
                         "sampling rate: " + str(int(self.sampling_rate)) + " per min")

    def _on_produced(self, produced_power_total: int):
        self.__produced_power_total = produced_power_total
        self.__notify_listeners()

    def _on_consumed(self, consumed_power_total: int):
        self.__consumed_power_total = consumed_power_total
        self.__notify_listeners()

    @property
    def current_power(self) -> int:
        return self.__current_power

    @property
    def average_produced_power(self) -> int:
        values = [power for power in self.__db.values() if power < 0]
        if len(values) > 0:
            return round(abs(sum(values) / len(values)))
        else:
            return 0

    @property
    def average_consumed_power(self) -> int:
        values = [power for power in self.__db.values() if power > 0]
        if len(values) > 0:
            return round(sum(values) / len(values))
        else:
            return 0

    @property
    def produced_power_total(self) -> int:
        return self.__produced_power_total

    @property
    def consumed_power_total(self) -> int:
        return self.__consumed_power_total



'''
logging.basicConfig(format='%(asctime)s %(name)-20s: %(levelname)-8s %(message)s', level=logging.DEBUG, datefmt='%Y-%m-%d %H:%M:%S')


meter = Meter("/dev/ttyUSB-meter",  10 * 60)

def on_data():
    print("current " + str(meter.current_power))
    print("smapling rate " + str(meter.sampling_rate))

meter.add_listener(on_data)


while True:
    sleep(10)
'''