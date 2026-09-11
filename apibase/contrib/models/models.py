from django.contrib.auth import get_user_model as USER

from . import methods

User = USER()

# get_user_model() が返すクラスに後付けする意図的なモンキーパッチ。
User.all_permissions = methods.User.all_permissions  # type: ignore[attr-defined]
