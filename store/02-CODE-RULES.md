# 02 - Code rules

Read this at the start of every session. These rules are what "done well" means here. A reviewer will hold your files against this list.

## Scope of a session

1. Build exactly what your task file names. Same file paths, same public names, same argument order. Other agents are writing code against those names right now.
2. Do not add features, options, files or dependencies the task does not ask for. If something seems missing, post an ASK and build the task as written.
3. Touch only the paths the task lists. Read other code only when the task tells you to.
4. If the task and a contract file disagree, the contract file wins: follow it and post a NOTE to humans naming both lines.
5. When about three quarters of your context is used and the task is not finished, stop adding code. Make what exists pass its check, save, and write what is left on your `next` line.

## Python

6. Every file starts with a module docstring of two to four lines: what the module does, who calls it, and what it must never do (for example "never imports torch").
7. The line `from __future__ import annotations` comes right after the docstring. Every function has type hints on all parameters and on the return value.
8. Every public function, class and method has a one-line docstring that says what it does in plain words. Add "Raises" only when it raises.
9. Names are whole words: `payload_length`, not `plen`. Put the unit in the name when there is one: `_bytes`, `_ms`, `_s`, `_count`.
10. A function does one thing and is at most about 40 lines. If you need a comment to mark "part two" of a function, make it two functions.
11. Data that crosses a module boundary travels in a dataclass or a typed tuple, never in a loose dict. JSON dicts exist only at the HTTP edge and the wire edge.
12. Constants are named in capitals at the top of the module, or come from `ecc/common/settings.py`. No bare numbers in the middle of code except 0, 1 and 2.
13. No module-level mutable state. An object gets what it needs through its constructor.
14. Imports: standard library, then third party, then `ecc`, separated by blank lines. No wildcard imports. No imports inside functions, with one exception: a module that must stay importable without torch imports torch inside the functions that need it.
14a. A class that you need only for a type hint, and that lives in a module another task delivers, is imported under `if typing.TYPE_CHECKING:` at the top of the file. Your module then still imports when that other module does not exist yet.
14b. Never run `pip`, `conda` or any installer, and never change `requirements.txt`. If an import of a pinned package fails, the wrong Python is running: stop and tell your human.
15. Comments say why, not what. Delete commented-out code.

## Errors and logging

16. Raise the project's exception types from `ecc/common/errors.py`. Never `except:` and never `except Exception: pass`. Catch the narrowest type, then either handle it fully or re-raise as a project exception with the original attached (`raise ... from error`).
17. Validate input where it enters the program (the wire, HTTP, files, the command line) and trust it after that. Do not re-check the same thing in every function.
18. Use `get_logger(__name__)` from `ecc/common/log.py`. `print` is allowed only in a mode's `main` function and in check scripts.
19. An error message says what was expected and what was found, with the values: `expected 3 tensors for expert (2, 5), found 2`.

## Threads

20. State at the top of each class which threads call it. Anything touched by more than one thread is guarded by one lock that belongs to the object that owns the data.
21. Never hold a lock while doing network input or output, file reads, or model computation. Copy what you need under the lock, release it, then do the slow work.
22. Every thread you start is a daemon thread with a name, and the object that started it has a `stop` or `close` method that ends it.

## Tensors and bytes

23. All multi-byte numbers on the wire and in files are little-endian. All arrays are row-major (C order) and contiguous before they become bytes.
24. Say the shape in a comment or docstring wherever a tensor or array is created or received: `# (rows, hidden)`.
25. Nothing in this project needs gradients. Every function that runs tensor computation applies `torch.no_grad()` itself and does not rely on its caller: the setting is per thread, and a new thread starts with gradients switched on. Use `no_grad`, not `inference_mode`.
25a. A weight matrix is stored with shape `(outputs, inputs)` and applied with `torch.nn.functional.linear`. Never store it the other way round and multiply with `@`: in 16-bit floats on a CPU that is about a thousand times slower.
26. Never compare floats with `==`. Use a tolerance and say which one.

## Check scripts

27. Each task adds one check script, run from the repo root as `python -B -m checks.<name>`. It needs no arguments, no internet and no other machine. It uses only `127.0.0.1` and picks free ports by binding to port 0.
28. For each thing it verifies it prints `PASS <short name>`. On the first failure it prints `FAIL <short name>: <what was expected and what was found>` and exits with code 1. On success its last line is `OK <file name> (<n> checks)` and it exits with code 0.
28a. A check always builds the master side and its satellites with device `cpu`, compute dtype `float32` and wire dtype `float32`, unless the assertion is about another dtype. Only then can numbers be compared exactly.
28b. A check does not depend on timing. It never sleeps and then hopes something happened: it calls the one-step method the task provides (`tick()`, `poll_once()`), or waits on a `threading.Event` with a generous limit. It never asserts that something took less than some number of milliseconds.
29. A check finishes in under 20 seconds, not counting Python start-up and imports, and leaves nothing behind: it stops the threads and servers it started and deletes the temporary files it made. Release a loaded model before deleting its folder, and ignore a deletion error: on Windows a weight file can stay locked for a moment.
30. A check tests behaviour through the public names in the task file, not private helpers. Never weaken or delete an assertion to make a check pass.

## JavaScript, HTML and CSS (the UI)

31. Plain ES modules loaded with `<script type="module">`. No framework, no bundler, no package manager, nothing loaded from another site.
32. One module owns one part of the page. Shared state lives in one store object in `main.js`; modules receive it and never keep their own copy of server data.
33. `const` by default, `let` when reassigned, never `var`. No inline event handlers in HTML. No `innerHTML` with server or user text: build elements and set `textContent`.
34. Rendering functions take state and draw; they do not fetch. Fetching lives in `api.js`.
35. Colours, sizes and timings are CSS custom properties or named constants, not repeated literals.

## Before you save

36. Run your check and the project Check. Read your own diff once from top to bottom and remove anything the task did not ask for.
37. Your PUSHED entry says exactly what you ran and what it printed. If something is a stub, the code says `STUB` and so does the entry.
