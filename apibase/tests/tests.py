import copy
import json

import yaml
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from apibase.utils import query

User = get_user_model()


class RestTestCase(TransactionTestCase):
    default_perms: list[str] = []

    def setUp(self):
        self.debug_print = False

    def create_client(self, user=None):
        client = APIClient()
        if user:
            client.force_authenticate(user=user)
            client.user = user
        return client

    def create_user(self, user_data, perms=None):
        if not user_data:
            return None
        user_data = copy.deepcopy(user_data)
        username = user_data.pop("username")

        user = User.objects.filter(username=username).first() or User.objects.create_user(
            username=username,
            email=user_data.get("email", f"{username}@localhost"),
            password=user_data.get("password", "password"),
        )

        if perms:
            user.user_permissions.add(*perms)
        user.user_data = user_data
        return user

    def requester(self, name=None, data=None, perms=None):
        user_data = name and data[name] or None
        user = self.create_user(user_data, perms=perms)
        return self.create_client(user)

    def assertResponse(self, response, code, message=""):
        if response.status_code != code:
            if response["Content-Type"] == "application/json":
                print(response.json())
            else:
                print(response.content)

        self.assertEqual(code, response.status_code, message)

    def Y(self, data, force=False):
        if force or getattr(self, "debug_print", False):
            print(self.to_yaml(data))

    def to_yaml(self, data):
        return yaml.dump(data, allow_unicode=True)

    def to_json(self, data, indent=2):
        return json.dumps(data, indent=indent)

    def graphql(self, path, **params):
        gql = open(path).read()
        return query(gql, **params)
