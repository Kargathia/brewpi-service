"""
Registers and gets features added to Aiohttp by brewblox services.
"""

from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import Any, Hashable, Type

from aiohttp import web

FEATURES_KEY = '#features'


def add(app: web.Application,
        feature: Any,
        key: Hashable=None,
        exist_ok: bool=False
        ):
    """
    Adds a new feature to the app.

    Features can either be registered as the default feature for the class,
    or be given an explicit name.

    Args:
        app (web.Application):
            The current Aiohttp application.

        feature (Any):
            The new feature that should be registered.
            It is recommended, but not required to use a `ServiceFeature`.

        key (Hashable, optional):
            The key under which the feature should be registered.
            Defaults to `type(feature)`.

        exist_ok (bool):
            If truthy, this function will do nothing if a feature was already registered for `key`.
            Otherwise, an exception is raised.

    """
    if FEATURES_KEY not in app:
        app[FEATURES_KEY] = dict()

    key = key or type(feature)

    if key in app[FEATURES_KEY]:
        if exist_ok:
            return
        else:
            raise KeyError(f'Feature "{key}" already registered')

    app[FEATURES_KEY][key] = feature


def get(app: web.Application,
        feature_type: Type[Any]=None,
        key: Hashable=None
        ) -> Any:
    """
    Finds declared feature.
    Identification is done based on feature type and key.

    Args:
        app (web.Application):
            The current Aiohttp application.

        feature_type (Type[Any]):
            The Python type of the desired feature.
            If specified, it will be checked against the found feature.

        key (Hashable):
            A specific identifier for the desired feature.
            Defaults to `feature_type`

    Returns:
        Any: The feature found for the combination of `feature_type` and `key`
    """
    key = key or feature_type

    if not key:
        raise AssertionError('No feature identifier provided')

    found = app.get(FEATURES_KEY, {}).get(key)

    if not found:
        raise KeyError(f'No feature found for "{key}"')

    if feature_type and not isinstance(found, feature_type):
        raise AssertionError(f'Found {found} did not match type "{feature_type}"')

    return found


class Startup(Enum):
    MANAGED = auto()
    MANUAL = auto()
    AUTODETECT = auto()


class ServiceFeature(ABC):
    """Base class for long-lived Aiohttp handler classes.

    For classes with async functionality,
    the (synchronous) `__init__()` and `__del__()` functions may not be sufficient.
    Aiohttp offers comparable init/deinit hooks, but inside the context of a running event loop.

    ServiceFeature registers the `self.startup(self, app)` and `self.shutdown(self, app)` as lifecycle callbacks.
    They will be called by Aiohttp at the appropriate moment.
    By overriding these functions, subclasses can perform initialization/deinitialization that requires an event loop.

    Note: Aiohttp will not accept registration of new callbacks after it started running.
    Startup management can be adjusted by using the `startup` argument in `ServiceFeature.__init__()`

    Example class:

        import asyncio
        import random
        from aiohttp import web
        from brewblox_service import scheduler, service
        from brewblox_service.features import ServiceFeature

        class MyFeature(ServiceFeature):

            def __init__(self, app: web.Application):
                super().__init__(app)
                self._task: asyncio.Task = None

            async def startup(self, app: web.Application):
                # Schedule a long-running background task
                self._task = await scheduler.create_task(app, self._hello())

            async def shutdown(self, app: web.Application):
                # Orderly cancel the background task
                await scheduler.cancel_task(app, self._task)

            async def _hello(self):
                while True:
                    await asyncio.sleep(5)
                    print(random.choice([
                        'Hellooo',
                        'Searching',
                        'Sentry mode activated',
                        'Is anyone there?',
                        'Could you come over here?',
                    ]))

    Example use:

        app = service.create_app(default_name='example')

        scheduler.setup(app)
        greeter = MyFeature(app)

        service.furnish(app)
        service.run(app)
        # greeter.startup(app) is called now

        # Press Ctrl+C to quit
        # greeter.shutdown(app) will be called
    """

    def __init__(self, app: web.Application, startup=Startup.AUTODETECT):
        """
        ServiceFeature constructor.

        Args:
            app (web.Application):
                The Aiohttp application with which the feature should be associated.

            startup (Startup):
                How feature lifecycle management should be handled. Default is AUTODETECT.
                    MANAGED:    Feature always registers lifecycle hooks.
                                This will raise an exception when creating
                                the feature while the application is running.

                    MANUAL:     Feature will not register lifecycle hooks.
                                startup() and shutdown() must be called manually.

                    AUTODETECT: Feature will register lifecycle hooks only if app is not running.
                                Behaves like MANAGED before application start,
                                and like MANUAL after application start.

        """
        self.__active_app: web.Application = app

        if any([
            startup == Startup.MANAGED,
            startup == Startup.AUTODETECT and not app.loop
        ]):
            app.on_startup.append(self.startup)
            app.on_cleanup.append(self.shutdown)

    @property
    def app(self) -> web.Application:
        """Currently active `web.Application`

        Returns:
            web.Application: The current app.
        """
        return self.__active_app

    @abstractmethod
    async def startup(self, app: web.Application):
        """Lifecycle hook for initializing the feature in an async context.

        Subclasses are expected to override this function.

        If `app` in the ServiceFeature.__init__(app) call was not None,
        startup() will be called when Aiohttp starts running.

        When this function is called, either by Aiohttp, or manually,
        `self.app` will be set to the current application.
        """
        pass  # pragma: no cover

    @abstractmethod
    async def shutdown(self, app: web.Application=None):
        """Lifecycle hook for shutting down the feature before the event loop is closed.

        Subclasses are expected to override this function.

        If `app` in the ServiceFeature.__init__(app) call was not None,
        shutdown() will be called when Aiohttp is closing, but before the event loop is closed.

        When this function is called, either by Aiohttp, or manually,
        `self.app` will be set to None.
        """
        pass  # pragma: no cover
