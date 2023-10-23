import serial
import logging
from abc import ABC, abstractmethod
from typing import List
from datetime import datetime, timedelta
from time import sleep
from threading import Thread
from smllib import SmlStreamReader
from smllib.sml import SmlGetListResponse
from redzoo.database.simple import SimpleDB


class DataListener(ABC):

    @abstractmethod
    def on_reset(self):
        pass

    @abstractmethod
    def on_read(self, data):
        pass

    @abstractmethod
    def on_read_error(self, e):
        pass


class SerialReader:

    def __init__(self,
                 port: str,
                 data_listener: DataListener,
                 read_timeout: int = 25):
        self.__logger = logging.getLogger(self.__class__.__name__)
        self.__data_listener = data_listener
        self.__port = port
        self.__read_timeout = read_timeout
        self.creation_date = datetime.now()
        self.last_time_data_received = datetime.now()
        self.is_running = False
        self.sensor = serial.Serial(self.__port, 9600, timeout=read_timeout)

    def start(self):
        self.__logger.info("opening " + self.__port)
        self.sensor.close()
        self.sensor.open()
        self.is_running = True
        Thread(target=self.__listen, daemon=True).start()

    def close(self, reason: str = ""):
        if self.is_running:
            self.is_running = False
            try:
                self.__logger.info("closing " + self.__port + " " + reason)
                self.sensor.close()
            except Exception as e:
                self.__logger.warning("error occurred closing " + str(self.__port) + " " + str(e))
            self.__data_listener.on_reset()

    def __listen(self):
        try:
            while self.is_running:
                data = self.sensor.read(200)   # blocks until enough data or read timeout
                if self.is_running:
                    if len(data) > 0:
                        self.last_time_data_received = datetime.now()
                        self.__data_listener.on_read(data)
                    else:
                        raise Exception("read timeout " + str(self.__read_timeout) + "sec exceeded")
        except Exception as e:
            if self.is_running:
                self.__data_listener.on_read_error(e)
                self.close("error: " + str(Exception("error occurred reading sensor data ", e)))
        finally:
            self.close()

    @property
    def elapsed_sec_since_data_received(self) -> float:
        return (datetime.now() - self.last_time_data_received).total_seconds()

    @property
    def elapsed_sec_since_created(self) -> float:
        return (datetime.now() - self.creation_date).total_seconds()


class ReconnectingSerialReader:

    def __init__(self, port: str, data_listener: DataListener, reconnect_period_sec: int = 15*60):
        self.__logger = logging.getLogger(self.__class__.__name__)
        self.is_running = True
        self.__port = port
        self.__data_listener = data_listener
        self.__reconnect_period_sec = reconnect_period_sec
        self.reader = SerialReader(port, data_listener)

    def __watchdog(self):
        while self.is_running:
            sleep(3)
            try:
                if self.reader.is_running:
                    if self.reader.elapsed_sec_since_data_received > 30:
                        ex = Exception("no data received since "+ str( self.reader.elapsed_sec_since_data_received) + " sec")
                        self.__data_listener.on_read_error(ex)
                        self.reader.close()
                    elif self.reader.elapsed_sec_since_created > self.__reconnect_period_sec:
                        self.reader.close("max connection time " + str(self.__reconnect_period_sec) + " sec exceeded")

                if not self.reader.is_running:
                    self.reader = SerialReader(self.__port, self.__data_listener, self.__reconnect_period_sec)
                    self.reader.start()
            except Exception as e:
                self.__logger.warning("error occurred processing watchdog " + str(e))
        self.__logger.warning("watchdog terminated")

    def start(self):
        self.reader.start()
        Thread(target=self.__watchdog, daemon=True).start()
        self.__logger.warning("watchdog started")

    def close(self):
        self.is_running = False
        self.reader.close()


class MeterProtocolReader(DataListener):

    def __init__(self,
                 port: str,
                 on_power_listener,
                 on_produced_listener,
                 on_consumed_listener,
                 on_error_listener,
                 reconnect_period_sec: int):
        self.__logger = logging.getLogger(self.__class__.__name__)
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

    def on_reset(self):
        self.__sml_stream_reader.clear()

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
                self.on_reset()
                self.__logger.warning(Exception("error occurred parsing frame", e))

    def on_read_error(self, e):
        self.on_reset()
        self.__on_error_listener(e)


class Meter:

    def __init__(self, port: str, reconnect_period_sec: int=90*60):
        self.__logger = logging.getLogger(self.__class__.__name__)
        self.__db = SimpleDB("meter_daily_power_values", sync_period_sec=10*60)
        self.__port = port
        self.__produced_power_total = 0
        self.__consumed_power_total = 0
        self.__listeners = set()
        self.__power_measurements: List[datetime] = []
        self.__current_power_measurement_time = datetime.now() - timedelta(days=1)
        self.__last_error_date = datetime.now() - timedelta(days=365)
        self.__last_reported_power = datetime.now() - timedelta(days=365)
        self.__current_power = self.average_produced_power
        self.__meter_values_reader = MeterProtocolReader(port, self._on_power, self._on_produced, self._on_consumed, self._on_error, reconnect_period_sec)
        self.__meter_values_reader.start()

    def add_listener(self, listener):
        self.__listeners.add(listener)

    def __notify_listeners(self):
        try:
            for listener in self.__listeners:
                listener()
        except Exception as e:
            self.__logger.warning("error occurred calling listener " + str(e))

    @property
    def sampling_rate(self) -> int:
        num_measurements = len(self.__power_measurements)
        if num_measurements > 1:
            elapsed_sec = (self.__power_measurements[-1] - self.__power_measurements[0]).total_seconds()
            return round((num_measurements / elapsed_sec) * 60)   # per  min
        else:
            return 0

    def __sample(self):
        now = datetime.now()
        self.__power_measurements.append(now)
        for i in range(0, len(self.__power_measurements)):
            if now > self.__power_measurements[0] + timedelta(seconds=120):
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
        self.__logger.warning("error occurred processing sensor data: " + str(e))
        self.__last_error_date = datetime.now()
        if datetime.now() > self.__current_power_measurement_time + timedelta(minutes=1):
            self.__current_power = self.average_produced_power    # reset to average
        self.__notify_listeners()

    def _on_power(self, current_power: int):
        self.__current_power = current_power
        self.__current_power_measurement_time = datetime.now()
        self.__notify_listeners()
        self.__db.put(self.__current_power_measurement_time.strftime("%H:%M"), current_power)
        self.__sample()
        self.__log_power_change()

    def __log_power_change(self):
        if datetime.now() > self.__last_reported_power + timedelta(seconds=30):
            self.__last_reported_power = datetime.now()
            self.__logger.info("current: " + str(self.__current_power) + " watt; " +
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
    pass

meter.add_listener(on_data)


while True:
    sleep(10)
'''