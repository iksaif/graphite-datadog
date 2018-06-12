from graphite.tags import base


class DataDogTagDB(base.BaseTagDB):
    def __init__(self, settings, *args, **kwargs):
        super(DataDogTagDB, self).__init__(settings, *args, **kwargs)

    def _find_series(self, tags, requestContext=None):
        return []

    def get_series(self, path, requestContext=None):
        return None

    def list_tags(self, tagFilter=None, limit=None, requestContext=None):
        return []

    def get_tag(self, tag, valueFilter=None, limit=None, requestContext=None):
        return None

    def list_values(self, tag, valueFilter=None, limit=None, requestContext=None):
        return []

    def tag_series(self, series, requestContext=None):
        raise NotImplementedError("Tagging not implemented with DummyTagDB")

    def del_series(self, series, requestContext=None):
        return True
