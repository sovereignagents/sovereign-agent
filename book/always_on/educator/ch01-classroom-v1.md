# Chapter 1 classroom materials

**Created:** 2026-09-08 · **Last-updated:** 2026-09-08 · **Status:** DRAFT classroom companion v1

Use this ninety-minute practical lesson alongside [Chapter 1](https://www.profrod.ai/book/ch01-first-model-call). You build a request from Lucy's shop data, reject malformed responses, challenge a plausible false answer and its checker, and detect a changed snapshot. The notebook contains the code; the instructor guide supplies preparation, timings, expected observations, an answer key, assessment and remediation.

- [Download the student notebook](https://gist.githubusercontent.com/profrod-principal/261a46c7a1509816006bef2f6d94ec1e/raw/3f8b113473f116b2bb332d16f3764ce28710e088/ch01-first-model-call-class-v1.ipynb)
- [Download the instructor guide and answer key](https://gist.githubusercontent.com/profrod-principal/261a46c7a1509816006bef2f6d94ec1e/raw/6769d12bdb81a686dcc1e0f3a2aaa5b2aaa910ff/ch01-instructor-guide-v1.md)

Open the `.ipynb` file in Colab or an existing Jupyter environment. Restart the kernel/runtime and Run all. Python 3.11 or newer and the standard library are sufficient; no installation, credential or model account is required. Keep `RUN_LIVE = False` for the offline class. The optional live experiment requires deliberate configuration and records a failure before falling back to an explicitly labelled fixture. The cumulative book uses Python 3.14.

Write a prediction before each experiment. Submit a malformed envelope and its rejection, a false claim missed by the warning heuristic, the stale-snapshot observation, and an assertion that Lime needs four tubs. A passing warning check never certifies arbitrary prose. The deterministic stock calculation and the draft response remain separate evidence.

The code has offline execution and adversarial regression checks. These do not substitute for a live provider observation, a hosted Colab run or a teacher's assessment of learner understanding. The material remains a draft. Source copies of both downloads live in `book/always_on/educator/` in the companion repository; the download URLs identify immutable file versions.
