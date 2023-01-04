from smartmeter_webthing.app import App, ArgumentSpec
from smartmeter_webthing.meter_webthing import run_server

def main():
    App.run(run_function=lambda args, desc: run_server(description=desc, port=args['port'], sport=args['sport']),
            packagename="smartmeter_webthing",
            arg_specs=[ArgumentSpec("sport", str, "the device port", True)])

if __name__ == '__main__':
    main()
