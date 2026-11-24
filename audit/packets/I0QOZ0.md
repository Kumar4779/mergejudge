# Packet I0QOZ0

## Problem statement

simplifying exponential -> trig identities
```
f = 1 / 2 * (-I*exp(I*k) + I*exp(-I*k))
trigsimp(f)
```

Ideally, this would yield `sin(k)`. Is there a way to do this?

As a corollary, it would be awesome if 

```
f = 1 / 2 / k* (-I*exp(I*k) + I*exp(-I*k))
trigsimp(f)
```

could yield `sinc(k)`. Thank you for your consideration!

## Patch

```diff
diff --git a/sympy/functions/elementary/trigonometric.py b/sympy/functions/elementary/trigonometric.py
index b2a3f3d..18283d2 100644
--- a/sympy/functions/elementary/trigonometric.py
+++ b/sympy/functions/elementary/trigonometric.py
@@ -408,6 +408,9 @@ def _eval_rewrite_as_csc(self, arg):
     def _eval_rewrite_as_sec(self, arg):
         return 1 / sec(arg - S.Pi / 2, evaluate=False)
 
+    def _eval_rewrite_as_sinc(self, arg):
+        return arg*sinc(arg)
+
     def _eval_conjugate(self):
         return self.func(self.args[0].conjugate())
 
diff --git a/sympy/simplify/trigsimp.py b/sympy/simplify/trigsimp.py
index 34a3bab..03e116d 100644
--- a/sympy/simplify/trigsimp.py
+++ b/sympy/simplify/trigsimp.py
@@ -538,6 +538,8 @@ def exp_trig(e):
         if e.has(*_trigs):
             choices.append(e.rewrite(exp))
         choices.append(e.rewrite(cos))
+        if e.is_Add:
+            choices.append(expand_mul(choices[-1]))
         return min(*choices, key=count_ops)
     newexpr = bottom_up(expr, exp_trig)
 
```
