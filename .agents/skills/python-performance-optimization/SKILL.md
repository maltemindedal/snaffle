---
name: python-performance-optimization
description: Profile Python CPU and memory use, find measured bottlenecks, and improve slow code without unnecessary rewrites.
---

# Python performance optimization

Measure Python CPU time and memory use, find the bottleneck, and change only
the code responsible for it.

## When to use this skill

- Identifying performance bottlenecks in Python applications
- Reducing application latency and response times
- Optimizing CPU-intensive operations
- Reducing memory consumption and memory leaks
- Improving database query performance
- Optimizing I/O operations
- Speeding up data processing pipelines
- Implementing high-performance algorithms
- Profiling production applications

## What to measure

### Profiling types

- CPU profiling identifies functions that consume the most time.
- Memory profiling tracks allocations and retained objects.
- Line profiling measures individual lines.
- A call graph shows which functions call one another.

### Metrics

- Execution time measures how long an operation takes.
- Memory usage includes peak and average consumption.
- CPU utilization measures processor use.
- I/O wait measures time blocked on input and output.

### Ways to improve performance

- Choose algorithms and data structures with lower cost.
- Remove repeated work from the implementation.
- Run independent work concurrently when the workload allows it.
- Cache expensive results when inputs repeat.
- Move measured hot paths to C or Rust when Python remains the bottleneck.

## Quick start

### Basic timing

```python
import time


def measure_time():
    """Simple timing measurement."""
    start = time.time()

    # Your code here
    result = sum(range(1000000))

    elapsed = time.time() - start
    print(f"Execution time: {elapsed:.4f} seconds")
    return result


# Use timeit for repeated measurements
import timeit

execution_time = timeit.timeit("sum(range(1000000))", number=100)
print(f"Average time: {execution_time / 100:.6f} seconds")
```

## Profiling tools

### Pattern 1: CPU profiling with cProfile

```python
import cProfile
import pstats
from pstats import SortKey


def slow_function():
    """Function to profile."""
    total = 0
    for i in range(1000000):
        total += i
    return total


def another_function():
    """Another function."""
    return [i**2 for i in range(100000)]


def main():
    """Main function to profile."""
    result1 = slow_function()
    result2 = another_function()
    return result1, result2


# Profile the code
if __name__ == "__main__":
    profiler = cProfile.Profile()
    profiler.enable()

    main()

    profiler.disable()

    # Print stats
    stats = pstats.Stats(profiler)
    stats.sort_stats(SortKey.CUMULATIVE)
    stats.print_stats(10)  # Top 10 functions

    # Save to file for later analysis
    stats.dump_stats("profile_output.prof")
```

#### Command-line profiling

```bash
# Profile a script
python -m cProfile -o output.prof script.py

# View results
python -m pstats output.prof
# In pstats:
# sort cumtime
# stats 10
```

### Pattern 2: line profiling with line_profiler

```python
# Install: pip install line-profiler

# Add @profile decorator (line_profiler provides this)
@profile
def process_data(data):
    """Process data with line profiling."""
    result = []
    for item in data:
        processed = item * 2
        result.append(processed)
    return result


# Run with:
# kernprof -l -v script.py
```

#### Manual line profiling

```python
from line_profiler import LineProfiler


def process_data(data):
    """Function to profile."""
    result = []
    for item in data:
        processed = item * 2
        result.append(processed)
    return result


if __name__ == "__main__":
    lp = LineProfiler()
    lp.add_function(process_data)

    data = list(range(100000))

    lp_wrapper = lp(process_data)
    lp_wrapper(data)

    lp.print_stats()
```

### Pattern 3: memory use with memory_profiler

```python
# Install: pip install memory-profiler

from memory_profiler import profile


@profile
def memory_intensive():
    """Function that uses lots of memory."""
    # Create large list
    big_list = [i for i in range(1000000)]

    # Create large dict
    big_dict = {i: i**2 for i in range(100000)}

    # Process data
    result = sum(big_list)

    return result


if __name__ == "__main__":
    memory_intensive()

# Run with:
# python -m memory_profiler script.py
```

### Pattern 4: production profiling with py-spy

```bash
# Install: pip install py-spy

# Profile a running Python process
py-spy top --pid 12345

# Generate flamegraph
py-spy record -o profile.svg --pid 12345

# Profile a script
py-spy record -o profile.svg -- python script.py

# Dump current call stack
py-spy dump --pid 12345
```

## Optimization patterns

### Pattern 5: list comprehensions and loops

```python
import timeit


# Slow: Traditional loop
def slow_squares(n):
    """Create list of squares using loop."""
    result = []
    for i in range(n):
        result.append(i**2)
    return result


# Fast: List comprehension
def fast_squares(n):
    """Create list of squares using comprehension."""
    return [i**2 for i in range(n)]


# Benchmark
n = 100000

slow_time = timeit.timeit(lambda: slow_squares(n), number=100)
fast_time = timeit.timeit(lambda: fast_squares(n), number=100)

print(f"Loop: {slow_time:.4f}s")
print(f"Comprehension: {fast_time:.4f}s")
print(f"Speedup: {slow_time / fast_time:.2f}x")


# Alternative implementation with map
def mapped_squares(n):
    """Create squares with map."""
    return list(map(lambda x: x**2, range(n)))
```

### Pattern 6: generator expressions

```python
import sys


def list_approach():
    """Memory-intensive list."""
    data = [i**2 for i in range(1000000)]
    return sum(data)


def generator_approach():
    """Memory-efficient generator."""
    data = (i**2 for i in range(1000000))
    return sum(data)


# Memory comparison
list_data = [i for i in range(1000000)]
gen_data = (i for i in range(1000000))

print(f"List size: {sys.getsizeof(list_data)} bytes")
print(f"Generator size: {sys.getsizeof(gen_data)} bytes")

# Generators use constant memory regardless of size
```

### Pattern 7: string concatenation

```python
import timeit


def slow_concat(items):
    """Slow string concatenation."""
    result = ""
    for item in items:
        result += str(item)
    return result


def fast_concat(items):
    """Fast string concatenation with join."""
    return "".join(str(item) for item in items)


def faster_concat(items):
    """Even faster with list."""
    parts = [str(item) for item in items]
    return "".join(parts)


items = list(range(10000))

# Benchmark
slow = timeit.timeit(lambda: slow_concat(items), number=100)
fast = timeit.timeit(lambda: fast_concat(items), number=100)
faster = timeit.timeit(lambda: faster_concat(items), number=100)

print(f"Concatenation (+): {slow:.4f}s")
print(f"Join (generator): {fast:.4f}s")
print(f"Join (list): {faster:.4f}s")
```

### Pattern 8: dictionary lookups and list searches

```python
import timeit

# Create test data
size = 10000
items = list(range(size))
lookup_dict = {i: i for i in range(size)}


def list_search(items, target):
    """O(n) search in list."""
    return target in items


def dict_search(lookup_dict, target):
    """O(1) search in dict."""
    return target in lookup_dict


target = size - 1  # Worst case for list

# Benchmark
list_time = timeit.timeit(lambda: list_search(items, target), number=1000)
dict_time = timeit.timeit(lambda: dict_search(lookup_dict, target), number=1000)

print(f"List search: {list_time:.6f}s")
print(f"Dict search: {dict_time:.6f}s")
print(f"Speedup: {list_time / dict_time:.0f}x")
```

### Pattern 9: local variable access

```python
import timeit

# Global variable (slow)
GLOBAL_VALUE = 100


def use_global():
    """Access global variable."""
    total = 0
    for i in range(10000):
        total += GLOBAL_VALUE
    return total


def use_local():
    """Use local variable."""
    local_value = 100
    total = 0
    for i in range(10000):
        total += local_value
    return total


# Local is faster
global_time = timeit.timeit(use_global, number=1000)
local_time = timeit.timeit(use_local, number=1000)

print(f"Global access: {global_time:.4f}s")
print(f"Local access: {local_time:.4f}s")
print(f"Speedup: {global_time / local_time:.2f}x")
```

### Pattern 10: function call overhead

```python
import timeit


def calculate_inline():
    """Inline calculation."""
    total = 0
    for i in range(10000):
        total += i * 2 + 1
    return total


def helper_function(x):
    """Helper function."""
    return x * 2 + 1


def calculate_with_function():
    """Calculation with function calls."""
    total = 0
    for i in range(10000):
        total += helper_function(i)
    return total


# Inline is faster due to no call overhead
inline_time = timeit.timeit(calculate_inline, number=1000)
function_time = timeit.timeit(calculate_with_function, number=1000)

print(f"Inline: {inline_time:.4f}s")
print(f"Function calls: {function_time:.4f}s")
```

For NumPy vectorization, caching, memory management, parallel execution, async
I/O, database queries, and benchmarks, see
[the advanced reference](references/advanced-patterns.md).

## Working rules

1. Profile before changing code.
2. Optimize measured hot paths.
3. Use dictionaries for keyed lookups and sets for membership checks.
4. Keep clear code until measurements justify added complexity.
5. Prefer built-in functions when they fit the job.
6. Use `lru_cache` when expensive calls repeat with the same inputs.
7. Batch I/O to reduce system calls.
8. Use generators when a collection does not need to be stored.
9. Measure NumPy for large numerical workloads.
10. Use `py-spy` to profile a running process.

## Common mistakes

- Optimizing without profiling
- Using global variables unnecessarily
- Not using appropriate data structures
- Creating unnecessary copies of data
- Not using connection pooling for databases
- Ignoring algorithmic complexity
- Over-optimizing rare code paths
- Not considering memory usage
