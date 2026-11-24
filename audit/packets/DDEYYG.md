# Packet DDEYYG

## Problem statement

Autoreloader with StatReloader doesn't track changes in manage.py.
Description
	 
		(last modified by Mariusz Felisiak)
	 
This is a bit convoluted, but here we go.
Environment (OSX 10.11):
$ python -V
Python 3.6.2
$ pip -V
pip 19.1.1
$ pip install Django==2.2.1
Steps to reproduce:
Run a server python manage.py runserver
Edit the manage.py file, e.g. add print(): 
def main():
	print('sth')
	os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ticket_30479.settings')
	...
Under 2.1.8 (and prior), this will trigger the auto-reloading mechanism. Under 2.2.1, it won't. As far as I can tell from the django.utils.autoreload log lines, it never sees the manage.py itself.

## Patch

```diff
diff --git a/django/utils/autoreload.py b/django/utils/autoreload.py
index 7ca0d68..fea3a79 100644
--- a/django/utils/autoreload.py
+++ b/django/utils/autoreload.py
@@ -114,7 +114,16 @@ def iter_modules_and_files(modules, extra_files):
         # During debugging (with PyDev) the 'typing.io' and 'typing.re' objects
         # are added to sys.modules, however they are types not modules and so
         # cause issues here.
-        if not isinstance(module, ModuleType) or getattr(module, '__spec__', None) is None:
+        if not isinstance(module, ModuleType):
+            continue
+        if module.__name__ == '__main__':
+            # __main__ (usually manage.py) doesn't always have a __spec__ set,
+            # so fall back to __file__.
+            filename = getattr(module, '__file__', None)
+            if filename:
+                sys_file_paths.append(filename)
+            continue
+        if getattr(module, '__spec__', None) is None:
             continue
         spec = module.__spec__
         # Modules could be loaded from places without a concrete location. If
```
