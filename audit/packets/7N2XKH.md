# Packet 7N2XKH

## Problem statement

Add easily comparable version info to toplevel
<!--
Welcome! Thanks for thinking of a way to improve Matplotlib.


Before creating a new feature request please search the issues for relevant feature requests.
-->

### Problem

Currently matplotlib only exposes `__version__`.  For quick version checks, exposing either a `version_info` tuple (which can be compared with other tuples) or a `LooseVersion` instance (which can be properly compared with other strings) would be a small usability improvement.

(In practice I guess boring string comparisons will work just fine until we hit mpl 3.10 or 4.10 which is unlikely to happen soon, but that feels quite dirty :))
<!--
Provide a clear and concise description of the problem this feature will solve. 

For example:
* I'm always frustrated when [...] because [...]
* I would like it if [...] happened when I [...] because [...]
* Here is a sample image of what I am asking for [...]
-->

### Proposed Solution

I guess I slightly prefer `LooseVersion`, but exposing just a `version_info` tuple is much more common in other packages (and perhaps simpler to understand).  The hardest(?) part is probably just bikeshedding this point :-)
<!-- Provide a clear and concise description of a way to accomplish what you want. For example:

* Add an option so that when [...]  [...] will happen
 -->

### Additional context and prior art

`version_info` is a pretty common thing (citation needed).
<!-- Add any other context or screenshots about the feature request here. You can also include links to examples of other programs that have something similar to your request. For example:

* Another project [...] solved this by [...]
-->

## Patch

```diff
diff --git a/lib/matplotlib/__init__.py b/lib/matplotlib/__init__.py
index b657a35..d9fc628 100644
--- a/lib/matplotlib/__init__.py
+++ b/lib/matplotlib/__init__.py
@@ -130,6 +130,32 @@ __bibtex__ = r"""@Article{Hunter:2007,
 }"""
 
 
+_VersionInfo = namedtuple('_VersionInfo',
+                          'major, minor, micro, releaselevel, serial')
+
+
+def _parse_to_version_info(version_str):
+    """
+    Parse a version string to a namedtuple analogous to sys.version_info.
+
+    See:
+    https://packaging.pypa.io/en/latest/version.html#packaging.version.parse
+    https://docs.python.org/3/library/sys.html#sys.version_info
+    """
+    v = parse_version(version_str)
+    if v.pre is None and v.post is None and v.dev is None:
+        return _VersionInfo(v.major, v.minor, v.micro, 'final', 0)
+    elif v.dev is not None:
+        return _VersionInfo(v.major, v.minor, v.micro, 'alpha', v.dev)
+    elif v.pre is not None:
+        releaselevel = {'a': 'alpha', 'b': 'beta', 'rc': 'candidate'}.get(
+            v.pre[0], 'alpha')
+        return _VersionInfo(v.major, v.minor, v.micro, releaselevel, v.pre[1])
+    else:
+        # fallback for v.post: guess-next-dev scheme from setuptools_scm
+        return _VersionInfo(v.major, v.minor, v.micro + 1, 'alpha', v.post)
+
+
 def __getattr__(name):
     if name == "__version__":
         import setuptools_scm
@@ -148,6 +174,10 @@ def __getattr__(name):
         else:  # Get the version from the _version.py setuptools_scm file.
             __version__ = _version.version
         return __version__
+    elif name == "__version_info__":
+        global __version_info__  # cache it.
+        __version_info__ = _parse_to_version_info(__getattr__("__version__"))
+        return __version_info__
     raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
 
 
```
