# Always-on agent educator companion

**Created:** 2026-09-08 · **Last-updated:** 2026-09-08 · **Status:** DRAFT educator companion v2

Use these corrected versions for new classes. The two Chapter 1 notebooks remain standalone Python 3.11 or newer with the standard library. Chapters 2–16 use the cumulative Python 3.14 checkout and locked book dependencies. The full book continues to publish on Prof Rod’s existing `/book` pages.

The runtime sources used by the copied-code experiments are pinned to commit `92db3d436dc69b5694eecb3adaebd82770f59250`, with individual SHA-256 checks. That historical commit alone does not contain the v2 educator files. The complete cohort checkout, including these corrections, is identified below once committed; use all files from that cohort together rather than mixing old helpers with new notebooks.

## Run a saved lesson

From the cohort checkout, open the notebook in an existing Python 3.14 notebook environment, or edit its saved cells and run:

```bash
uv run --python 3.14 python book/always_on/educator/run_lesson_v2.py --chapter 2 --output /tmp/lucy-ch02-v2.json
```

For your own saved copy, add `--notebook /absolute/path/student.ipynb`. The runner executes trusted local Python; it is not a sandbox. Use a new evidence filename on each run. Chapter 1’s second lesson uses `--chapter 1 --follow-on`. No package is added by the runner.

## Downloads

Each link below names an immutable revision, checked anonymously against its source bytes. There are seventeen notebooks and seventeen instructor guides. Previously distributed v1 files remain historical records; keep their live mode off and use the corrected v2 transport for new live exercises.

| Chapter | Topic | Student materials | Instructor materials |
| --- | --- | --- | --- |
| 1 | First model call | [Notebook](https://gist.githubusercontent.com/profrod-principal/ac7669a7604d2a0e281677360b28d516/raw/f7891eb423d77ef4c5002bbde719278c43e7d156/ch01-first-model-call-class-v2.ipynb) · [Follow-on](https://gist.githubusercontent.com/profrod-principal/ac7669a7604d2a0e281677360b28d516/raw/e011526813e459a5cd0cf0c1dc9945590b0bbf56/ch01-prompts-and-harness-class-v2.ipynb) | [Guide](https://gist.githubusercontent.com/profrod-principal/ac7669a7604d2a0e281677360b28d516/raw/5d4adeb44134be4fb709d07af92f07749196f2df/ch01-instructor-guide-v2.md) · [Follow-on guide](https://gist.githubusercontent.com/profrod-principal/ac7669a7604d2a0e281677360b28d516/raw/245ea808b1b7f5aeca5f87c76b514bdc0c026170/ch01-prompts-and-harness-instructor-guide-v2.md) |
| 2 | Give the agent reliable shop tools | [Notebook](https://gist.githubusercontent.com/profrod-principal/ac7669a7604d2a0e281677360b28d516/raw/7d00b9e623a50d28131ac2c46b16efc33cd55ff3/ch02-shop-tools-class-v2.ipynb) | [Guide and answers](https://gist.githubusercontent.com/profrod-principal/ac7669a7604d2a0e281677360b28d516/raw/2fee5e02f5a073994ba13cd6c5a408d2a3051916/ch02-instructor-guide-v2.md) |
| 3 | Build the model and tool loop | [Notebook](https://gist.githubusercontent.com/profrod-principal/ac7669a7604d2a0e281677360b28d516/raw/f27e9a614d803befe66037ea9a760f06ec9b97dc/ch03-agent-loop-class-v2.ipynb) | [Guide and answers](https://gist.githubusercontent.com/profrod-principal/ac7669a7604d2a0e281677360b28d516/raw/890c881e52abfc0f93daf7df433939062b598fde/ch03-instructor-guide-v2.md) |
| 4 | Remember across conversations | [Notebook](https://gist.githubusercontent.com/profrod-principal/ac7669a7604d2a0e281677360b28d516/raw/22daf71d828f17b63cc2362b305144d8c0e86c29/ch04-memory-class-v2.ipynb) | [Guide and answers](https://gist.githubusercontent.com/profrod-principal/ac7669a7604d2a0e281677360b28d516/raw/43066735a51c819d235a1b4f5d60105592aa6d3a/ch04-instructor-guide-v2.md) |
| 5 | Reuse a tested opening procedure | [Notebook](https://gist.githubusercontent.com/profrod-principal/ac7669a7604d2a0e281677360b28d516/raw/4def971b332896bb1c0d851dad0e8602c2a13a92/ch05-skills-class-v2.ipynb) | [Guide and answers](https://gist.githubusercontent.com/profrod-principal/ac7669a7604d2a0e281677360b28d516/raw/345bbe76c3b79a0ec4fbf230a23dc72420c011ba/ch05-instructor-guide-v2.md) |
| 6 | Talk to the agent from your phone | [Notebook](https://gist.githubusercontent.com/profrod-principal/ac7669a7604d2a0e281677360b28d516/raw/2ad7fe22674b9d02d0642ff07059100ee07d47db/ch06-messaging-class-v2.ipynb) | [Guide and answers](https://gist.githubusercontent.com/profrod-principal/ac7669a7604d2a0e281677360b28d516/raw/93ec83f9bd72f11f3a459a3902877e296f766e98/ch06-instructor-guide-v2.md) |
| 7 | Wake up for schedules and stock events | [Notebook](https://gist.githubusercontent.com/profrod-principal/ac7669a7604d2a0e281677360b28d516/raw/2a092ec35be3ca1ec42e0e1883550f42f5352ba0/ch07-scheduling-class-v2.ipynb) | [Guide and answers](https://gist.githubusercontent.com/profrod-principal/ac7669a7604d2a0e281677360b28d516/raw/c8e1de700392e52d144e3a73803ecfed972392f1/ch07-instructor-guide-v2.md) |
| 8 | Ask permission before spending | [Notebook](https://gist.githubusercontent.com/profrod-principal/ac7669a7604d2a0e281677360b28d516/raw/f71d7fcf8b166fa89a3601c801694aa66d527b6b/ch08-approval-class-v2.ipynb) | [Guide and answers](https://gist.githubusercontent.com/profrod-principal/ac7669a7604d2a0e281677360b28d516/raw/1b549ddac5a81eff2fd8c5915196e141a5df9b06/ch08-instructor-guide-v2.md) |
| 9 | Survive the ambiguous supplier order | [Notebook](https://gist.githubusercontent.com/profrod-principal/ac7669a7604d2a0e281677360b28d516/raw/fc3b5549e2632554fa0fd99199776261aea2cbfb/ch09-ambiguous-order-class-v2.ipynb) | [Guide and answers](https://gist.githubusercontent.com/profrod-principal/ac7669a7604d2a0e281677360b28d516/raw/d7369628575eff9678ca2c389ebfeaa06d93dbbb/ch09-instructor-guide-v2.md) |
| 10 | Recover work after a process crash | [Notebook](https://gist.githubusercontent.com/profrod-principal/ac7669a7604d2a0e281677360b28d516/raw/d1ad210303746a4b714a2126bd965da23c12d459/ch10-worker-recovery-class-v2.ipynb) | [Guide and answers](https://gist.githubusercontent.com/profrod-principal/ac7669a7604d2a0e281677360b28d516/raw/85a0098604836afa13b434ba56ae5f98f97a4652/ch10-instructor-guide-v2.md) |
| 11 | Isolate tools and untrusted content | [Notebook](https://gist.githubusercontent.com/profrod-principal/ac7669a7604d2a0e281677360b28d516/raw/e6f5323b7a1d658897b27f7e089871009dd076ee/ch11-isolation-class-v2.ipynb) | [Guide and answers](https://gist.githubusercontent.com/profrod-principal/ac7669a7604d2a0e281677360b28d516/raw/e88411cad2051d00bbc2168ba252c5e8d3b48167/ch11-instructor-guide-v2.md) |
| 12 | Measure whether the agent helps | [Notebook](https://gist.githubusercontent.com/profrod-principal/ac7669a7604d2a0e281677360b28d516/raw/748a9fe5d727a381001d75bc7dcd4156bec9d106/ch12-evaluation-class-v2.ipynb) | [Guide and answers](https://gist.githubusercontent.com/profrod-principal/ac7669a7604d2a0e281677360b28d516/raw/af6a0c1988ab7dd4075195dde7079129a6de8fb6/ch12-instructor-guide-v2.md) |
| 13 | Improve behavior with evaluated changes | [Notebook](https://gist.githubusercontent.com/profrod-principal/ac7669a7604d2a0e281677360b28d516/raw/0b764501d4ed2cb1c7e372b7d7a3c9933decf508/ch13-improvement-class-v2.ipynb) | [Guide and answers](https://gist.githubusercontent.com/profrod-principal/ac7669a7604d2a0e281677360b28d516/raw/7be3b9f4609df74ec4e261601e9b3e09a1fe3226/ch13-instructor-guide-v2.md) |
| 14 | Delegate one bounded task | [Notebook](https://gist.githubusercontent.com/profrod-principal/ac7669a7604d2a0e281677360b28d516/raw/077614f2882416c625688903df8de867246210e2/ch14-delegation-class-v2.ipynb) | [Guide and answers](https://gist.githubusercontent.com/profrod-principal/ac7669a7604d2a0e281677360b28d516/raw/5ba10ca6dc187273a3b2ab44181d8911ac193e0e/ch14-instructor-guide-v2.md) |
| 15 | Deploy and maintain the agent | [Notebook](https://gist.githubusercontent.com/profrod-principal/ac7669a7604d2a0e281677360b28d516/raw/1c87482e55ed0d5c360c61c33e8b7b452a7a9e2f/ch15-operation-class-v2.ipynb) | [Guide and answers](https://gist.githubusercontent.com/profrod-principal/ac7669a7604d2a0e281677360b28d516/raw/0bdd33a4d9b22ebc573efd5cb1de92652995c987/ch15-instructor-guide-v2.md) |
| 16 | Lucy leaves the shop for a day | [Notebook](https://gist.githubusercontent.com/profrod-principal/ac7669a7604d2a0e281677360b28d516/raw/e21bf909c32879e117665013b8ba2eb35ce4eec2/ch16-acceptance-class-v2.ipynb) | [Guide and answers](https://gist.githubusercontent.com/profrod-principal/ac7669a7604d2a0e281677360b28d516/raw/405000b27298fd7c3b60f6f21038213dcdaa030a/ch16-instructor-guide-v2.md) |

## What students build and prove

For Chapters 2–16, allow ten minutes for a decision-function warm-up and forty-five minutes for the central copied-code experiment. Students inspect real source and a visible probe, predict a specific failure, mutate only the temporary copy, repair it, and retain a `file:line → observed field` explanation. Each chapter has its own business consequence, real mutation, independently authored expectations, transfer task and teacher answer key. The optional full checkpoint remains separate reference evidence.

Untouched student work remains NOT_SUBMITTED. Unsupported return types retain a FAILED diagnostic without breaking the report. Partial work is explicitly PARTIAL. Input mutation is reported even when the returned value matches. Visible-case lookup tables can pass visible tests; teachers must inspect the implementation, ask novel cases and assess the real repair. A worked solution never overwrites the original student grade or source.

Chapter 3 provides an executable integration cell for the student’s own ReplayModel, Limits and failing model. It retains stop reason, calls, configured exposure and actual tool messages separately from the pure admission exercise. A failed attempt is still an attempt; the estimate is not a provider invoice.

The local runtime trials require no model/channel credentials. Chapter 9 uses a separate loopback supplier process and independent SQLite receipts; other central trials exercise local Python and SQLite. Full checkpoints can additionally launch workers, an MCP process or a real SIGKILL experiment as their guides specify. None of these defaults performs a real purchase, sends Telegram messages, installs a service or establishes host uptime or OS containment.

## Chapter 1 pacing and safety

The first lesson is planned for ninety minutes. The operator used its opening thirty-minute core before the sixty-minute prompts-and-harness follow-on; that is a valid shortened sequence, not completion of the entire first lesson. The follow-on also works after the full first lesson.

The v2 HTTP helpers refuse redirects, including a second local origin, and require an assistant-role completion. Role shape does not authenticate a model. A good model may resist a hostile note in all observed live trials; forced compromised responses still test Python enforcement. Authored responses cannot establish model failure frequencies or prompt quality.

## Observe the class

Use the source file `book/always_on/educator/classroom-pilot-record-v1.md` to collect anonymous first attempts, actual completion times, setup errors, assistance, source repairs and transfer explanations. The guides include the rubric and explain how to retain evidence. No student pilot outcomes have been fabricated: the reported thirty-minute distribution is the only operator classroom observation supplied so far.

These remain draft teaching materials. Executable checks, teacher rehearsal, observed learning, human visual review and publisher acceptance are separate evidence. No new book rendering location is introduced.
