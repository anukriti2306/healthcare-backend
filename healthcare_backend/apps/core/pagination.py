from rest_framework.pagination import LimitOffsetPagination


class OptionalLimitOffsetPagination(LimitOffsetPagination):
    """
    Pagination that only kicks in when the client asks for it.

    * ``GET /api/patients/``                    -> plain JSON array (all rows)
    * ``GET /api/patients/?limit=10&offset=20`` -> ``{count, next, previous, results}``
    """

    default_limit = None
    max_limit = 100
