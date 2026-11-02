from guardian.models import FileChange

BAD_PATCH = """@@ -1,3 +1,9 @@
 import os
+import boto3
+
+API_KEY = "sk-ant-abcdefghijklmnopqrstuvwxyz123456"
+
+def GetUser(id):
+    print("debug", id)
+    # TODO fix later
+    return db.query(id)
"""

BAD_FILE = FileChange("app/services/UserService.py", "added", BAD_PATCH, additions=8)
CLEAN_FILE = FileChange("app/services/user_service.py", "modified",
                        "@@ -1,2 +1,3 @@\n import logging\n+\n+LOG = logging.getLogger(__name__)\n", 2)
BAD_COMMITS = ["added stuff"]


class FakeLLM:
    def __init__(self, reply=None, exc=None):
        self.reply, self.exc, self.prompts = reply, exc, []

    def complete(self, system, user):
        self.prompts.append(user)
        if self.exc:
            raise self.exc
        return self.reply


class FakeGH:
    def __init__(self, files, messages, conventions="# reglas"):
        self.files, self.messages, self.conventions = files, messages, conventions
        self.statuses, self.comments = [], []

    def changed_files(self, repo, before, after):
        return self.files, self.messages

    def get_file(self, repo, path, ref):
        return self.conventions

    def set_status(self, repo, sha, state, description, **kw):
        self.statuses.append((state, description))

    def comment_commit(self, repo, sha, body):
        self.comments.append(body)
