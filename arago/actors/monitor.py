import gevent.hub
import signal
from functools import partial
from arago.actors.actor import Actor
from arago.actors.actor import ActorStoppedError

class ExitPolicy(object):
	def __init__(self, identifier):
		self.__ident__ = identifier
	def __str__(self):
		return self.__ident__

IGNORE = ExitPolicy("IGNORE") # ignore child crashes
RESUME = ExitPolicy("RESUME") # resume the exited child
RESTART = ExitPolicy("RESTART") # restart the exited child
RESTART_REST = ExitPolicy("RESTART_REST") # restart the exited child and all that came after it (in order)
RESTART_REST_REVERSE = ExitPolicy("RESTART_REST_REVERSE") # restart the exited child and all that came after it (in reverse order)
RESTART_ALL = ExitPolicy("RESTART_ALL") # restart all children (in order)
RESTART_ALL_REVERSE = ExitPolicy("RESTART_ALL_REVERSE") # restart all children (in reverse order)
ESCALATE = ExitPolicy("ESCALATE") # if a child stops, stop all children and yourself
DEPLETE = ExitPolicy("DEPLETE") # if the last child stops, stop all children and yourself
SHUTDOWN = ExitPolicy("SHUTDOWN") # shutdown crashed children
SHUTDOWN_ALL = ExitPolicy("SHUTDOWN_ALL") # shutdown all children

class Monitor(Actor):
	def __init__(self, name=None, policy=RESTART, max_restarts=None, timeframe=None, children=None, *args, **kwargs):
		super().__init__(name=name, *args, **kwargs)
		self._policy = policy
		self._children = []
		([self.register_child(child) for child in children]
		 if children else None)

	def _handle_child(self, child, state):
		self._logger.debug("{ch}, a child of {me}, stopped, policy is {pol}".format(ch=child, me=self, pol=self._policy))
		if self._policy == RESTART:
			child.clear()
			child.start()

		elif self._policy == RESUME:
			child.start()

		elif self._policy == SHUTDOWN:
			self._logger.warn("{ch}, a child of {me}, stopped, shutting it down ...".format(me=self, ch=child))
			self.unregister_child(child)
			if state == "crashed":
				child.clear()

		elif self._policy == ESCALATE:
			self._logger.error("{ch}, a child of {me}, stopped, escalating ...".format(me=self, ch=child))
			self.unregister_child(child)
			if state == "crashed":
				child.clear()
			self._kill()

		elif self._policy == IGNORE:
			self._logger.warn("{ch}, a child of {me}, stopped, ignoring ...".format(me=self, ch=child))
			self.unregister_child(child)
			if state == "crashed":
				child.clear()

		elif self._policy == DEPLETE:
			self.unregister_child(child)
			if state == "crashed":
				child.clear()
			if len(self._children.greenlets) <= 1:
				self._logger.error("{ch}, last child of {me}, stopped, escalating ...".format(me=self, ch=child))
				self._kill()

	def spawn_child(self, cls, *args, **kwargs):
		"""Start an instance of cls(*args, **kwargs) as child"""
		child = cls(*args, **kwargs)
		self.logger.debug("{me} spawned new child {ch}".format(me=self, ch=child))
		self._register_child(child)

	def register_child(self, child):
		"""Register an already running Actor as child"""
		if isinstance(child, partial):
			child = child()
		self._children.append(child)
		#child.link(self._handle_child_exit)
		child.register_parent(self)
		self._logger.debug("{ch} registered as child of {me}.".format(ch=child, me=self))

	def unregister_child(self, child):
		"""Unregister a running Actor from the list of children"""
		#child.unlink(self._handle_child_exit)
		self._children.remove(child)
		self._logger.debug("{ch} unregistered as child of {me}.".format(ch=child, me=self))

	def resume(self):
		[child.resume() for child in self._children]
		super().resume()

	def restart(self):
		[child.restart() for child in self._children]
		super().restart()

	def shutdown(self):
		[child.shutdown() for child in self._children]
		super().shutdown()

class Root(Monitor):
	def __init__(self, join=True, *args, **kwargs):
		super().__init__(*args, **kwargs)
		gevent.hub.signal(signal.SIGINT, self.shutdown)
		gevent.hub.signal(signal.SIGTERM, self.shutdown)
		if join:
			self.join()


	def join(self):
		self._loop.join()
