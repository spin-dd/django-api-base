import json

from .. import models
from . import exec_query


def export_groups():
    q = """
        query GroupSet {
            group_set {
                edges {
                    node {
                        pk, name
                        permissions {
                            edges {
                                node {
                                    pk, codename, name
                                    content_type {
                                        app_label, model
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        """
    res = exec_query(q)
    return json.dumps(res)


def import_groups(path):
    data = json.load(open(path))
    for edge in data["group_set"]["edges"]:
        group, _ = models.Group.objects.get_or_create(name=edge["node"]["name"])
        for edge2 in edge["node"]["permissions"]["edges"]:
            defaults = {"name": edge2["node"]["name"]}
            content_type = models.ContentType.objects.filter(**edge2["node"]["content_type"]).first()
            if content_type:
                permission, _ = models.Permission.objects.update_or_create(
                    defaults, codename=edge2["node"]["codename"], content_type=content_type
                )
                group.permissions.add(permission)
