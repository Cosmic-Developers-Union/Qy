"""Example: Using the Qy runtime with custom operators."""

from qy import Qy

qy = Qy()

# Register custom pure operators
qy.register_pure("inc", lambda x: x + 1, doc="Increment by 1.")
qy.register_pure("dec", lambda x: x - 1, doc="Decrement by 1.")
qy.register_pure("max", lambda a, b: a if a >= b else b, doc="Return the larger of two numbers.")
qy.register_pure("min", lambda a, b: a if a <= b else b, doc="Return the smaller of two numbers.")
qy.register_pure("abs", lambda x: -x if x < 0 else x, doc="Absolute value.")
qy.register_pure("zero?", lambda x: x == 0, doc="Check if zero.")
qy.register_pure("positive?", lambda x: x > 0, doc="Check if positive.")
qy.register_pure("negative?", lambda x: x < 0, doc="Check if negative.")
qy.register_pure("even?", lambda x: x % 2 == 0, doc="Check if even.")
qy.register_pure("odd?", lambda x: x % 2 != 0, doc="Check if odd.")
qy.register_pure(
    "range",
    lambda n: tuple(range(n)),
    doc="Create a tuple of integers from 0 to n-1.",
)
qy.register_pure("len", lambda x: len(x) if isinstance(x, tuple) else 0, doc="Length of a list.")


# Now use them in Qy expressions
print(qy.evaluate_source("(inc 5)"))  # 6
print(qy.evaluate_source("(dec 10)"))  # 9
print(qy.evaluate_source("(max 3 7)"))  # 7
print(qy.evaluate_source("(min 3 7)"))  # 3
print(qy.evaluate_source("(abs (- 5))"))  # 5
print(qy.evaluate_source("(zero? 0)"))  # True
print(qy.evaluate_source("(positive? 42)"))  # True
print(qy.evaluate_source("(even? 4)"))  # True
print(qy.evaluate_source("(odd? 7)"))  # True
print(qy.evaluate_source("(range 5)"))  # (0, 1, 2, 3, 4)
print(qy.evaluate_source("(len '(a b c))"))  # 3

# Compose with built-in operators
print(qy.evaluate_source("(* (inc 3) (dec 5))"))  # 4 * 4 = 16
print(qy.evaluate_source("(max (square 3) (square 4))"))  # needs square

# Define functions that use custom operators
qy.evaluate_source("(defun clamp (x lo hi) (max lo (min x hi)))")
print(qy.evaluate_source("(clamp 50 0 100)"))  # 50
print(qy.evaluate_source("(clamp -5 0 100)"))  # 0
print(qy.evaluate_source("(clamp 150 0 100)"))  # 100

qy.evaluate_source("(defun safe-div (a b) (cond ((zero? b) 0) (true (/ a b))))")
print(qy.evaluate_source("(safe-div 10 3)"))  # 3.333...
print(qy.evaluate_source("(safe-div 10 0)"))  # 0

# Use let with custom operators
print(qy.evaluate_source("(let ((x -7)) (abs x))"))  # 7
print(qy.evaluate_source("(let ((xs '(1 2 3 4 5))) (len xs))"))  # 5


# Register an evaluation operator (special form)
@qy.register_evaluation("when")
def _when(args, env):
    """Evaluate body only when condition is truthy."""
    from qy.evaluator import evaluate as _eval

    if len(args) < 2:
        raise ValueError("when expects a condition and at least one body form")
    condition = _eval(args[0], env)
    if condition not in (False, None, ()):
        result = None
        for form in args[1:]:
            result = _eval(form, env)
        return result
    return None


print(qy.evaluate_source('(when true "it is true")'))  # "it is true"
print(qy.evaluate_source('(when false "should not appear")'))  # None

# Run a full program
results = qy.evaluate_program(
    """
(defund fibonacci (n)
  (cond
    ((zero? n) 0)
    ((eq n 1) 1)
    (true (+ (fibonacci (- n 1)) (fibonacci (- n 2))))))

(fibonacci 10)
"""
)
print(results)  # [..., 55]
