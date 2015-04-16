import argparse
import logging
import sys
import signal
import os
import django

import gevent.event

from gthulhu.log import log
import gthulhu.log

try:
    import manhole
except ImportError:
    manhole = None

if __name__ == "__main__":

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "usm.settings")
    django.setup()

    parser = argparse.ArgumentParser(description='Calamari management service')
    parser.add_argument('--debug', dest='debug', action='store_true',
                        default=False, help='print log to stdout')

    args = parser.parse_args()
    if args.debug:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(gthulhu.log.FORMAT))
        log.addHandler(handler)

    # Instruct salt to use the gevent version of ZMQ
    import zmq.green
    import salt.utils.event
    salt.utils.event.zmq = zmq.green

    # Set up gevent compatibility in psycopg2
    import psycogreen.gevent
    psycogreen.gevent.patch_psycopg()

    if manhole is not None:
        # Enable manhole for debugging.  Use oneshot mode
        # for gevent compatibility
        manhole.cry = lambda message: log.info("MANHOLE: %s" % message)
        manhole.install(oneshot_on=signal.SIGUSR1)

    from gthulhu.manager import Manager
    m = Manager()
    m.start()
    print "Started Manager"
    complete = gevent.event.Event()

    def shutdown():
        log.info("Signal handler: stopping")
        complete.set()

    gevent.signal(signal.SIGTERM, shutdown)
    gevent.signal(signal.SIGINT, shutdown)

    while not complete.is_set():
        complete.wait(timeout=1)
