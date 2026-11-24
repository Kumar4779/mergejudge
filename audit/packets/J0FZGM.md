# Packet J0FZGM

## Problem statement

Migration auth.0011_update_proxy_permissions fails for models recreated as a proxy.
Description
	 
		(last modified by Mariusz Felisiak)
	 
I am trying to update my project to Django 2.2. When I launch python manage.py migrate, I get this error message when migration auth.0011_update_proxy_permissions is applying (full stacktrace is available ​here):
django.db.utils.IntegrityError: duplicate key value violates unique constraint "idx_18141_auth_permission_content_type_id_01ab375a_uniq" DETAIL: Key (co.ntent_type_id, codename)=(12, add_agency) already exists.
It looks like the migration is trying to re-create already existing entries in the auth_permission table. At first I though it cloud because we recently renamed a model. But after digging and deleting the entries associated with the renamed model from our database in the auth_permission table, the problem still occurs with other proxy models.
I tried to update directly from 2.0.13 and 2.1.8. The issues appeared each time. I also deleted my venv and recreated it without an effect.
I searched for a ticket about this on the bug tracker but found nothing. I also posted this on ​django-users and was asked to report this here.

## Patch

```diff
diff --git a/django/contrib/auth/migrations/0011_update_proxy_permissions.py b/django/contrib/auth/migrations/0011_update_proxy_permissions.py
index 0e66649..6275ddf 100644
--- a/django/contrib/auth/migrations/0011_update_proxy_permissions.py
+++ b/django/contrib/auth/migrations/0011_update_proxy_permissions.py
@@ -24,10 +24,15 @@ def update_proxy_model_permissions(apps, schema_editor, reverse=False):
         proxy_content_type = ContentType.objects.get_for_model(Model, for_concrete_model=False)
         old_content_type = proxy_content_type if reverse else concrete_content_type
         new_content_type = concrete_content_type if reverse else proxy_content_type
+        # Skip permissions already present for the new content type (e.g. a
+        # model recreated as a proxy) to avoid unique constraint violations.
+        existing_codenames = Permission.objects.filter(
+            content_type=new_content_type,
+        ).values('codename')
         Permission.objects.filter(
             permissions_query,
             content_type=old_content_type,
-        ).update(content_type=new_content_type)
+        ).exclude(codename__in=existing_codenames).update(content_type=new_content_type)
 
 
 def revert_proxy_model_permissions(apps, schema_editor):
```
