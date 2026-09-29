from .settings import *  # noqa: F401,F403

# 本地无 PostgreSQL，测试用内存 sqlite；模型与迁移代码不变
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
