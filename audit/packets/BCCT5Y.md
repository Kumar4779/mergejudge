# Packet BCCT5Y

## Problem statement

ccode(sinc(x)) doesn't work
```
In [30]: ccode(sinc(x))
Out[30]: '// Not supported in C:\n// sinc\nsinc(x)'
```

I don't think `math.h` has `sinc`, but it could print

```
In [38]: ccode(Piecewise((sin(theta)/theta, Ne(theta, 0)), (1, True)))
Out[38]: '((Ne(theta, 0)) ? (\n   sin(theta)/theta\n)\n: (\n   1\n))'
```

## Patch

```diff
diff --git a/sympy/printing/ccode.py b/sympy/printing/ccode.py
index 30a07a7b59..722f44034f 100644
--- a/sympy/printing/ccode.py
+++ b/sympy/printing/ccode.py
@@ -218,6 +218,20 @@ def _print_ITE(self, expr):
         _piecewise = Piecewise((expr.args[1], expr.args[0]), (expr.args[2], True))
         return self._print(_piecewise)
 
+    def _print_Relational(self, expr):
+        lhs_code = self._print(expr.lhs)
+        rhs_code = self._print(expr.rhs)
+        op = expr.rel_op
+        return "{0} {1} {2}".format(lhs_code, op, rhs_code)
+
+    def _print_sinc(self, expr):
+        from sympy.functions.elementary.trigonometric import sin
+        from sympy.core.relational import Ne
+        from sympy.functions import Piecewise
+        _piecewise = Piecewise(
+            (sin(expr.args[0]) / expr.args[0], Ne(expr.args[0], 0)), (1, True))
+        return self._print(_piecewise)
+
     def _print_MatrixElement(self, expr):
         return "{0}[{1}]".format(expr.parent, expr.j +
                 expr.i*expr.parent.shape[1])
```
