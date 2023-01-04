from webthing import (SingleThing, Property, Thing, Value, WebThingServer)
import logging
import tornado.ioloop
from smartmeter_webthing.meter import Meter



class SmartMeterThing(Thing):

    # regarding capabilities refer https://iot.mozilla.org/schemas
    # there is also another schema registry http://iotschema.org/docs/full.html not used by webthing
    def __init__(self, description: str, meter: Meter):
        Thing.__init__(
            self,
            'urn:dev:ops:SmartMeter-1',
            'SmartMeter',
            ['MultiLevelSensor'],
            description
        )

        self.meter = meter

        self.current_power = Value(meter.current_power)
        self.add_property(
            Property(self,
                     'current_power',
                     self.current_power,
                     metadata={
                         'title': 'current power',
                         "type": "number",
                         'description': 'The current power [Watt]',
                         'readOnly': True,
                     }))

        self.produced_power_total = Value(meter.produced_power_total)
        self.add_property(
            Property(self,
                     'produced_power_total',
                     self.produced_power_total,
                     metadata={
                         'title': 'produced power total',
                         "type": "number",
                         'description': 'The total produced power [Watt]',
                         'readOnly': True,
                     }))

        self.consumed_power_total = Value(meter.consumed_power_total)
        self.add_property(
            Property(self,
                     'consumed_power_total',
                     self.consumed_power_total,
                     metadata={
                         'title': 'consumed power total',
                         "type": "number",
                         'description': 'The total consumed power [Watt]',
                         'readOnly': True,
                     }))


        self.ioloop = tornado.ioloop.IOLoop.current()
        self.meter.add_listener(self.on_value_changed)

    def on_value_changed(self):
        self.ioloop.add_callback(self.__on_value_changed)

    def __on_value_changed(self):
        self.current_power.notify_of_external_update(self.meter.current_power)
        self.consumed_power_total.notify_of_external_update(self.meter.consumed_power_total)
        self.produced_power_total.notify_of_external_update(self.meter.produced_power_total)


def run_server(description: str, port: int, sport: str):
    meter = Meter(sport)
    server = WebThingServer(SingleThing(SmartMeterThing(description, meter)), port=port, disable_host_validation=True)
    logging.info('running webthing server http://localhost:' + str(port))
    try:
        server.start()
    except KeyboardInterrupt:
        logging.info('stopping webthing server')
        server.stop()
        logging.info('done')

