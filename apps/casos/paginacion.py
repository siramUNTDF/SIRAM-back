from rest_framework.pagination import PageNumberPagination


class PaginacionEstandar(PageNumberPagination):
    """`?page=2&page_size=50`. Respuesta: { count, next, previous, results }."""

    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 200
