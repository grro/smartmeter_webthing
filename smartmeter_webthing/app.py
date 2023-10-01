from os import system, remove
from os import listdir
import pathlib
import logging
import subprocess
import argparse
from dataclasses import dataclass
from importlib.metadata import metadata, entry_points
from typing import List, Any, Dict



class Unit:

    UNIT_TEMPLATE = '''
    [Unit]
    Description=$packagename
    After=syslog.target
    
    [Service]
    Type=simple
    ExecStart=$entrypoint --command listen $params
    SyslogIdentifier=$packagename
    StandardOutput=syslog
    StandardError=syslog
    Restart=on-failure
    RestartSec=3
    
    [Install]
    WantedBy=multi-user.target
    '''


    def __init__(self, packagename: str):
        self.packagename = packagename

    def __print_status(self, service: str):
        try:
            status = subprocess.check_output("sudo systemctl is-active " + service, shell=True, stderr=subprocess.STDOUT)
            if status.decode('ascii').strip() == 'active':
                print(service + " is running")
                print("try sudo journalctl -f -n 50 -u " + service)
                return
        except subprocess.CalledProcessError as e:
            pass
        print("Warning: " + service + " is not running")
        system("try sudo journalctl -f -n 50 -u " + service)

    def register(self, entrypoint: str, port: int, args: Dict[str, Any]):
        service = self.servicename(port)
        replacements = {'packagename': self.packagename, 'entrypoint': entrypoint}
        unit = Unit.UNIT_TEMPLATE
        params = []
        for name in args.keys():
            if name != "command":
                params.append("--" + name + " " + str(args[name]))
        replacements['params'] = " ".join(params)
        for name in replacements.keys():
            unit = unit.replace("$" + name, replacements[name])
        unit_file_fullname = str(pathlib.Path("/", "etc", "systemd", "system", service))
        with open(unit_file_fullname, "w") as file:
            file.write(unit)
        system("sudo systemctl daemon-reload")
        system("sudo systemctl enable " + service)
        system("sudo systemctl restart " + service)
        self.__print_status(service)

    def deregister(self, port: int):
        service = self.servicename(port)
        unit_file_fullname = str(pathlib.Path("/", "etc", "systemd", "system", service))
        system("sudo systemctl stop " + service)
        system("sudo systemctl disable " + service)
        system("sudo systemctl daemon-reload")
        try:
            remove(unit_file_fullname)
        except Exception as e:
            pass

    def printlog(self, port: int):
        service = self.servicename(port)
        cmd = "sudo journalctl -f -u " + service
        logging.info(cmd)
        system(cmd)

    def servicename(self, port: int):
        return self.packagename + "_" + str(port) + ".service"

    def list_installed(self):
        services = []
        try:
            for file in listdir(pathlib.Path("/", "etc", "systemd", "system")):
                if file.startswith(self.packagename) and file.endswith('.service'):
                    idx = file.rindex('_')
                    port = str(file[idx+1:file.index('.service')])
                    services.append((file, port, self.is_active(file)))
        except Exception as e:
            pass
        return services

    def is_active(self, servicename: str):
        cmd = '/bin/systemctl status %s' % servicename
        proc = subprocess.Popen(cmd, shell=True,stdout=subprocess.PIPE,encoding='utf8')
        stdout_list = proc.communicate()[0].split('\n')
        for line in stdout_list:
            if 'Active:' in line:
                if '(running)' in line:
                    return True
        return False


@dataclass
class ArgumentSpec:
    name: str
    dt: type
    description: str
    required: bool = False
    default_value: Any = None

    def resolve(self, args):
        return vars(args)[self.name]


class App:

    @staticmethod
    def run(run_function, packagename: str, arg_specs: List[ArgumentSpec], default_port: int = 8644):
        App(run_function, packagename, arg_specs, default_port).handle_command()

    def __init__(self,run_function, packagename: str, arg_specs: List[ArgumentSpec], default_port: int):
        self.unit = Unit(packagename)
        self.run_function = run_function
        self.packagename = packagename
        self.arg_specs = arg_specs
        self.default_port = default_port
        md = metadata(packagename)
        self.description = md.get('description', "")
        for script in entry_points()['console_scripts']:
            if script.value == packagename + ':main':
                self.entrypoint = script.name
        print(self.description)

    def parse_arguments(self) -> Dict[str, Any]:
        parser = argparse.ArgumentParser(description=self.description)
        parser.add_argument('--command', metavar='command', required=False, type=str, help='the command. Supported commands are: listen (run the webthing service), register (register and starts the webthing service as a systemd unit, deregister (deregisters the systemd unit), log (prints the log)')
        parser.add_argument('--port', metavar='port', required=False, type=int, default=self.default_port, help='the port of the webthing serivce')
        parser.add_argument('--verbose', metavar='verbose', required=False, type=bool, default=False, help='activates verbose output')
        for spec in self.arg_specs:
            parser.add_argument('--' + spec.name, metavar=spec.name, required=False, type=spec.dt, default=spec.default_value, help=spec.description)
        args = parser.parse_args()

        arguments = {"port": args.port, "verbose": args.verbose, "command": args.command}
        for arg_spec in self.arg_specs:
            arguments[arg_spec.name] = arg_spec.resolve(args)
        return arguments

    def check_params(self, args:  Dict[str, Any]) -> bool:
        for spec in self.arg_specs:
            if spec.required and args.get(spec.name, None) is None:
                print("parameter --" + spec.name + " has to be set (" + spec.description + ")\n")
                return False
        return True

    def handle_command(self):
        args = self.parse_arguments()
        if args['verbose']:
            log_level=logging.DEBUG
        else:
            log_level=logging.INFO
        print("set log level " + str(log_level))
        logging.basicConfig(format='%(asctime)s %(name)-20s: %(levelname)-8s %(message)s', level=log_level, datefmt='%Y-%m-%d %H:%M:%S')
        logging.getLogger('tornado.access').setLevel(logging.ERROR)
        logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)

        handled = False
        if args.get('command', None) is None:
            print("parameter --command has to be set\n")
        elif args['command'] == 'log':
            self.unit.printlog(args['port'])
        elif args['command'] == 'listen':
            if self.check_params(args):
                handled = self.do_listen(args['port'], args)
        elif args['command'] == 'register':
            if self.check_params(args):
                handled = self.do_register(args['port'],args)
        elif args['command'] == 'deregister':
            handled = self.do_deregister(args['port'])
        else:
            print("unsupported command " + str(args['command']) + "\n")
        if not handled:
            self.do_print_usage_info(args)

    def do_print_usage_info(self, args: Dict[str, Any]) -> bool:
        print("for command options usage")
        print(" sudo " + self.entrypoint + " --help")
        print("example commands")
        print(" sudo " + self.entrypoint + " --command register --port " + str(args['port']) + " " + " ".join(["--" + argument.name + " " + str(argument.default_value) if argument.default_value is not None else "..." for argument in self.arg_specs]))
        print(" sudo " + self.entrypoint + " --command listen --port " + str(args['port']) + " " +  " ".join(["--" + argument.name + " " + str(argument.default_value) if argument.default_value is not None else "..." for argument in self.arg_specs]))
        if len(self.unit.list_installed()) > 0:
            print("example commands for registered services")
            for service_info in self.unit.list_installed():
                port = service_info[1]
                print(" sudo " + self.entrypoint + " --command deregister --port " + port)
                print(" sudo " + self.entrypoint + " --command log --port " + port)
        return True

    def do_listen(self, port: int, args: Dict[str, Any]) -> bool:
        print('starting webthing server on port ' + str(port))
        self.run_function(args, self.description)
        return True

    def do_register(self, port: int, args: Dict[str, Any]) -> bool:
        print('register and starting webthing server on port ' + str(port))
        Unit(self.packagename).register(self.entrypoint, port, args)
        return True

    def do_deregister(self, port: int) -> bool:
        print('deregister ' + str(port))
        Unit(self.packagename).deregister(port)
        return True
