# Packet 4CZXU7

## Problem statement

`Pow.as_real_imag` is inconsistent with evaluating `Pow(0, -1)` as ComplexInfinity

> Another example of something causing this issue: `1/Sum(1, (Symbol("p"), 8, 6))`
> 
> I think this boils down to the following inconsistency:
> - `Pow(0,-1).as_real_imag() == (nan, nan)`
> - `Sum(1, (Symbol("p"), 8, 6)).is_nonzero is None`
> - `Pow(Sum(1, (Symbol("p"), 8, 6)), -1).as_real_imag() == (Pow(Sum(1, (Symbol("p"), 8, 6)), -1), 0)`
> 
> I guess https://github.com/sympy/sympy/blob/c0adb406785d80e9b4bbe1f0c95e7357f371bb53/sympy/core/power.py#L1130-L1137 should have a case first about what to do if `not self.base.is_nonzero` when `not exp >= 0` 

 _Originally posted by @JasonGross in [#28218](https://github.com/sympy/sympy/issues/28218#issuecomment-3047313998)_

## Patch

```diff
diff --git a/sympy/core/power.py b/sympy/core/power.py
index cc9e900..cb282e1 100644
--- a/sympy/core/power.py
+++ b/sympy/core/power.py
@@ -1133,7 +1133,7 @@ def as_real_imag(self, deep=True, **hints):
 
             exp = self.exp
             re_e, im_e = self.base.as_real_imag(deep=deep)
-            if not im_e:
+            if not im_e and (exp >= 0 or self.base.is_zero is False):
                 return self, S.Zero
             a, b = symbols('a b', cls=Dummy)
             if exp >= 0:
```
