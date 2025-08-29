from rest_framework.pagination import PageNumberPagination

class SimplePagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 100

def get_paginated_data(queryset, request, serializer_class):
    paginator = SimplePagination()
    paginated_qs = paginator.paginate_queryset(queryset, request)
    serializer = serializer_class(paginated_qs, many=True)
    return {
        "data": serializer.data,
        "page": paginator.page.number,
        "page_size": paginator.page.paginator.per_page,
        "total": paginator.page.paginator.count,
        "has_next": paginator.page.has_next(),
        "has_previous": paginator.page.has_previous(),
    }
