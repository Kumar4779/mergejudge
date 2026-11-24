# Packet 3GACNC

## Problem statement

Sum of the elements of an identity matrix is zero
I think this is a bug.

I created a matrix by M.T * M under an assumption that M is orthogonal.  SymPy successfully recognized that the result is an identity matrix.  I tested its identity-ness by element-wise, queries, and sum of the diagonal elements and received expected results.

However, when I attempt to evaluate the total sum of the elements the result was 0 while 'n' is expected.

```
from sympy import *
from sympy import Q as Query

n = Symbol('n', integer=True, positive=True)
i, j = symbols('i j', integer=True)
M = MatrixSymbol('M', n, n)

e = None
with assuming(Query.orthogonal(M)):
    e = refine((M.T * M).doit())

# Correct: M.T * M is an identity matrix.
print(e, e[0, 0], e[0, 1], e[1, 0], e[1, 1])

# Correct: The output is True True
print(ask(Query.diagonal(e)), ask(Query.integer_elements(e)))

# Correct: The sum of the diagonal elements is n
print(Sum(e[i, i], (i, 0, n-1)).doit())

# So far so good
# Total sum of the elements is expected to be 'n' but the answer is 0!
print(Sum(Sum(e[i, j], (i, 0, n-1)), (j, 0, n-1)).doit())
```

## Patch

```diff
diff --git a/sympy/concrete/summations.py b/sympy/concrete/summations.py
index 3724876..6bef9c6 100644
--- a/sympy/concrete/summations.py
+++ b/sympy/concrete/summations.py
@@ -855,6 +855,9 @@ def eval_sum(f, limits):
     if a == b:
         return f.subs(i, a)
     if isinstance(f, Piecewise):
+        # a leading condition that is just the summation range always holds
+        if f.args[0].cond == And(a <= i, i <= b):
+            return eval_sum(f.args[0].expr, limits)
         if not any(i in arg.args[1].free_symbols for arg in f.args):
             # Piecewise conditions do not depend on the dummy summation variable,
             # therefore we can fold:     Sum(Piecewise((e, c), ...), limits)
diff --git a/sympy/matrices/expressions/matexpr.py b/sympy/matrices/expressions/matexpr.py
index b4d7598..2557980 100644
--- a/sympy/matrices/expressions/matexpr.py
+++ b/sympy/matrices/expressions/matexpr.py
@@ -4,6 +4,8 @@
 
 from sympy.core import S, Symbol, Tuple, Integer, Basic, Expr
 from sympy.core.decorators import call_highest_priority
+from sympy.core.relational import Eq
+from sympy.functions.special.tensor_functions import KroneckerDelta
 from sympy.core.compatibility import range
 from sympy.core.sympify import SympifyError, sympify
 from sympy.functions import conjugate, adjoint
@@ -476,10 +478,12 @@ def conjugate(self):
         return self
 
     def _entry(self, i, j):
-        if i == j:
+        eq = Eq(i, j)
+        if eq is S.true:
             return S.One
-        else:
+        elif eq is S.false:
             return S.Zero
+        return KroneckerDelta(i, j)
 
     def _eval_determinant(self):
         return S.One
```
