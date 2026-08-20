# Wallet test suite

A single black-box test suite for measuring the functional correctness of every
generated build of the payments wallet. It talks to a build only through the
fixed HTTP contract, so the same suite runs unchanged against all nine builds.

## How it works

The suite never imports or inspects a build's code. It starts from the endpoint
contract that was given to every model, sends real HTTP requests, and checks the
responses. This is what makes it a fair, identical measurement across builds: any
build that followed the contract can be tested by it, and any build that ignored
the contract fails for that reason, which is itself a valid result.

Success is checked strictly against the contract's success status codes.
Rejection is checked loosely: because the task instruction left error responses
to each model's discretion, a rejected request is treated as "not a success",
and, where money is involved, is confirmed by checking that no balance changed.

## Running it against one build

1. Start the build's server. Note the address it listens on (often
   `http://localhost:8000`).

2. From this folder, install the suite's own dependencies (once):

   ```
   pip install -r requirements.txt
   ```

3. Point the suite at the running build and run it:

   ```
   BASE_URL=http://localhost:8000 pytest
   ```

   On Windows PowerShell:

   ```
   $env:BASE_URL="http://localhost:8000"; pytest
   ```

Each test prints a pass or fail line, and the run ends with a summary such as
`28 passed, 4 failed`. Record the number passed and the list of failures for
that build.

## Recording results

For each of the nine builds, record:

* the number of tests passed out of the total, as the functional-correctness
  score for that build;
* which specific tests failed, since the pattern of failures is what shows
  where a condition helped or did not.

### A build that will not run

Some builds may not start at all: a missing file, an invented dependency, a
broken import. In that case the suite cannot connect and every test errors.
Record this as a distinct outcome, not simply as zero passed:

* score it as zero for functional correctness, and
* flag it separately as a build failure, and
* note the cause, since an invented package or missing file is also relevant to
  the hallucination dimension.

"Did not run" is a meaningfully different result from "ran but got things wrong",
and the two should be distinguished in the analysis.

## What the suite does and does not measure

It measures functional correctness: whether the build behaves as the
requirements and business rules specify. It does **not** measure code quality,
security, or hallucinations directly; those are assessed separately by static
analysis and manual review, though a build that fails to run for want of an
invented package will surface in both this suite and the hallucination review.

Two requirement aspects cannot be checked black box and are deliberately left to
the other evaluation dimensions or noted as limitations: the internal storage of
passwords (NFR1, seen only in that the password is never echoed back), the atomic
writing of ledger entries (NFR5), and the reset of the rolling daily window after
24 hours (BR3), which cannot be tested without manipulating time.
