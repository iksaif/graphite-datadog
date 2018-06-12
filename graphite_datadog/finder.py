import threading
import datetime
import time

import datadog

from graphite import node
from graphite.finders import utils

from graphite_datadog import errors
from graphite_datadog import glob_utils


def init_api(settings):
    """Initialize the datadog API.

    Args:
          settings: Django settings or None.

    Return:
          datadog.api
    """
    if not settings:
        from django.conf import settings

    options = {"api_key": settings.DATADOG_API_KEY, "app_key": settings.DATADOG_APP_KEY}
    print(options)
    datadog.initialize(**options)

    return datadog.api


def deduplicate(entries):
    """Yield items once only."""
    yielded = set()
    for entry in entries:
        if entry not in yielded:
            yielded.add(entry)
            yield entry


class DataDogFinder(utils.BaseFinder):
    """DataDog finder.

    See utils.BaseFinder for the API.

    Currently pretty inefficient, need to understand how to do
    server side filtering and bulk_queries to make it better.

    Goal for this first version is just to list metrics and fetch a few points.
    """

    def __init__(self, *args, **kwargs):
        """Create the finder."""
        super(DataDogFinder, self).__init__()
        self._api = None
        self._lock = threading.Lock()
        self._api = kwargs.get("api", None)
        self._settings = kwargs.get("settings", None)

    @property
    def api(self):
        """API accessor."""
        with self._lock:
            if not self._api:
                self._api = init_api(self._settings)
        return self._api

    def find_nodes(self, query):
        """Get the list of nodes matching a query.

        Args:
          graphite.storage.FindQuery: the query to run.

        Returns:
          generator of Node
        """
        # TODO: with time.now() it returns 0, maybe try to use 'window' like the UI.
        start_time = query.startTime or time.mktime(datetime.datetime.utcnow().timetuple()) - 3600

        pattern = query.pattern

        # TODO: try to do some server-side filtering
        result = self.api.Metric.list(from_epoch=start_time)

        if not result or "errors" in result:
            raise errors.DataDogError(result.get("errors"))

        for node in deduplicate(self.metrics_to_nodes(result["metrics"], pattern)):
            yield node

    def metrics_to_nodes(self, metrics, pattern):
        """Filter metrics and convert to nodes."""

        # From a metric list, infer directories.
        # TODO: This is super super inefficient!
        directories = set()
        for metric in metrics:
            components = metric.split(".")
            for i in range(1, len(components)):
                directories.add('.'.join(components[:i]))

        # Then filter everything accoring to the pattern.
        for directory in glob_utils.glob(directories, pattern):
            yield node.BranchNode(directory)

        for metric in glob_utils.glob(metrics, pattern):
            yield node.LeafNode(metric, None)
