import os

import gevent.event

try:
    import msgpack
except ImportError:
    msgpack = None

from gthulhu import salt_config

from gthulhu.log import log
from gthulhu import djangoUtil

from usm_common.salt_wrapper import SaltEventSource


class TopLevelEvents(gevent.greenlet.Greenlet):
    def __init__(self, manager):
        super(TopLevelEvents, self).__init__()

        self._manager = manager
        self._complete = gevent.event.Event()

    def stop(self):
        self._complete.set()

    def _run(self):
        log.info("%s running" % self.__class__.__name__)

        event = SaltEventSource(log, salt_config)
        while not self._complete.is_set():
            ev = event.get_event(full=True)
            if ev is not None and 'tag' in ev:
                tag = ev['tag']
                data = ev['data']
                try:
                    if tag.startswith("salt/auth"):
                        log.debug("Tag: %s Data: %s" % (tag, data))
                        if djangoUtil.check_minion_is_new(data['id']):
                            djangoUtil.add_minion_to_free_pool(data['id'])
                        else:
                            log.debug(
                                "Ignoring - Already added to the free pool")
                    else:
                        # This does not concern us, ignore it
                        log.debug("TopLevelEvents: ignoring %s" % tag)
                        pass
                except:
                    log.exception("Exception handling message tag=%s" % tag)

        log.info("%s complete" % self.__class__.__name__)


class Manager(object):
    """
    Manage a collection of ClusterMonitors.

    Subscribe to ceph/cluster events, and create a ClusterMonitor
    for any FSID we haven't seen before.
    """

    def __init__(self):
        self._complete = gevent.event.Event()

        # self._rpc_thread = RpcThread(self)
        self._discovery_thread = TopLevelEvents(self)
        # self._process_monitor = ProcessMonitorThread()

        # self.notifier = NotificationThread()

        # Remote operations
        # self.requests = RequestCollection(self)
        # self._request_ticker = Ticker(request_collection.TICK_PERIOD,
        #                              lambda: self.requests.tick())

        # FSID to ClusterMonitor
        # self.clusters = {}

        # Generate events on state changes
        # self.eventer = Eventer(self)

        # Handle all ceph/server messages
        # self.servers = ServerMonitor(
        #    self.persister, self.eventer, self.requests)

    def delete_cluster(self, fs_id):
        """
        Note that the cluster will pop right back again if it's
        still sending heartbeats.
        """
        victim = self.clusters[fs_id]
        victim.stop()
        victim.done.wait()
        del self.clusters[fs_id]

        self._expunge(fs_id)

    def stop(self):
        log.info("%s stopping" % self.__class__.__name__)
        # for monitor in self.clusters.values():
        #    monitor.stop()
        # self._rpc_thread.stop()
        self._discovery_thread.stop()
        # self._process_monitor.stop()
        # self.notifier.stop()
        # self.eventer.stop()
        # self._request_ticker.stop()

    def _expunge(self, fsid):
        # session = Session()
        # session.query(SyncObject).filter_by(fsid=fsid).delete()
        # session.commit()
        pass

    def _recover(self):
            pass

    def start(self):
        log.info("%s starting" % self.__class__.__name__)

        # Before we start listening to the outside world, recover
        # our last known state from persistent storage
        try:
            self._recover()
        except:
            log.exception("Recovery failed")
            os._exit(-1)

        # self._rpc_thread.bind()
        # self._rpc_thread.start()
        self._discovery_thread.start()
        # self._process_monitor.start()
        # self.notifier.start()
        # self.persister.start()
        # self.eventer.start()
        # self._request_ticker.start()

        # self.servers.start()

    def join(self):
        log.info("%s joining" % self.__class__.__name__)
        # self._rpc_thread.join()
        self._discovery_thread.join()
        # self._process_monitor.join()
        # self.notifier.join()
        # self.persister.join()
        # self.eventer.join()
        # self._request_ticker.join()
        # self.servers.join()
        # for monitor in self.clusters.values():
        #    monitor.join()

    def on_discovery(self, minion_id, heartbeat_data):
        log.info(
            "on_discovery: {0}/{1}".format(minion_id, heartbeat_data['fsid']))
        # cluster_monitor = ClusterMonitor(
        #    heartbeat_data['fsid'],
        #    heartbeat_data['name'],
        #    self.notifier,
        #    self.persister,
        #    self.servers,
        #    self.eventer,
        #    self.requests)
        # self.clusters[heartbeat_data['fsid']] = cluster_monitor

        # Run before passing on the heartbeat, because otherwise the
        # syncs resulting from the heartbeat might not be received
        # by the monitor.
        # cluster_monitor.start()
        # Wait for ClusterMonitor to start accepting events before asking it
        # to do anything
        # cluster_monitor.ready()
        # cluster_monitor.on_heartbeat(minion_id, heartbeat_data)


def dump_stacks():
    """
    This is for use in debugging, especially using manhole
    """
    pass
