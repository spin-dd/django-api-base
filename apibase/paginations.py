from collections import OrderedDict

from rest_framework import pagination, response


class Pagination(pagination.PageNumberPagination):
    page_size = 16
    max_page_size = 200
    page_size_query_param = "page_size"

    def get_paginated_response(self, data):
        start = max(1, self.page.number - 5)
        end = min(self.page.paginator.num_pages, self.page.number + 5)
        return response.Response(
            OrderedDict(
                [
                    ("count", self.page.paginator.count),
                    ("page_range", list(range(start, end + 1))),
                    ("current_page", self.page.number),
                    ("next", self.get_next_link()),
                    ("previous", self.get_previous_link()),
                    ("results", data),
                ]
            )
        )
