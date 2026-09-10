"""DRF pagination classes (presentation layer).

Transactions use cursor-based pagination (stable feed); everything else uses
``page``/``page_size``.
"""

from rest_framework.pagination import CursorPagination as DRFCursorPagination
from rest_framework.pagination import PageNumberPagination as DRFPageNumberPagination


class PageNumberPagination(DRFPageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
    page_query_param = "page"


class CursorPagination(DRFCursorPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
    ordering = "-created_at"
