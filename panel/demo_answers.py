"""Scripted candidate answers for `panel demo`.

Keyed by competency rather than held in a flat list: the conductor decides what
to ask next, so a positional script drifts out of alignment the moment a probe
fires, and later competencies end up answered with material written for earlier
ones.

The answers are deliberately uneven — strong ones, thin ones, and a genuine
non-answer — so a single run exercises every branch of the conductor and
produces a report with a real spread of levels instead of a flat one.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Callable

NO_MORE = "That's about as far as I can take that one."

DEMO_ANSWERS: dict[str, list[str]] = {
    "ownership": [
        # Strong: specific, first-person, quantified outcome, systemic fix.
        "Our deploy pipeline had been flaky for months and everyone just retried it. "
        "Nobody owned it. I spent two days instrumenting the runner and found 80 percent "
        "of failures came from a race in how we cached node_modules. I decided to fix "
        "the cache key rather than add another retry, and I added an assertion that "
        "fails the build loudly if the cache is stale. Failure rate went from about 30 "
        "percent of builds to under 2 percent, and it stayed there.",
        # Thin: duties, no instance, no outcome.
        "I was responsible for the billing service. We had an on-call rotation and I "
        "handled my share of the pages like everyone else on the team.",
    ],
    "problem_solving": [
        "We had to migrate 40 million rows to a new schema with no downtime. I started "
        "by writing down what 'no downtime' actually meant, which turned out to be under "
        "200ms of added latency. I considered a big-bang migration in a maintenance "
        "window, but we ruled it out because the business wouldn't accept the window. "
        "Instead we dual-wrote for two weeks, backfilled in batches, then flipped reads. "
        "The constraint that shaped everything was that we couldn't take a write lock.",
        "My first framing was wrong, actually. I assumed the bottleneck was write "
        "throughput, and in hindsight I should have profiled before designing. It turned "
        "out to be index rebuild time. Next time I'd measure before committing to a shape.",
    ],
    "communication": [
        # Weak: no through-line, undefined jargon, point never arrives.
        "So there's the ingest layer and then the normaliser, and the normaliser talks "
        "to the enrichment service over gRPC, and there's a Kafka topic in between that "
        "we use for replay, and the whole thing feeds into the warehouse, and then "
        "there's a separate path for the realtime stuff which uses a different codec.",
        # Genuine non-answer — exercises the non-substantive branch.
        "I don't know.",
        "I was explaining a caching bug to our head of sales. I started with the API "
        "internals and lost her in about thirty seconds. I stopped and restarted with "
        "what she actually cared about: customers were seeing yesterday's prices for up "
        "to an hour. Once I led with that, the conversation took two minutes.",
    ],
    "systems_tradeoffs": [
        "The dominant constraint was read latency — we had a 50ms p99 budget at the "
        "edge. We put a read-through cache in front of Postgres and accepted staleness "
        "of up to 60 seconds, which cost us correctness on the pricing page during "
        "promotions. That was the tradeoff we took knowingly. It breaks down at about 40 "
        "thousand requests per second, where cache stampedes on eviction start "
        "saturating the origin.",
        "If traffic went up a hundred times we'd probably need to shard. We'd look at "
        "adding more replicas and maybe moving to a different database.",
    ],
    "debugging": [
        "We had a data corruption bug that only appeared under load. My hypothesis was a "
        "concurrency issue in the writer, and the thing that would have falsified it was "
        "seeing corruption in single-threaded runs — which we didn't. I bisected by "
        "disabling one worker pool at a time until it reproduced with just two writers, "
        "then read that path closely. The proximate cause was a missing lock. The reason "
        "it was possible was that the type didn't distinguish shared from owned state, "
        "so I changed the signature to make the unsafe call impossible.",
        "Production-only bugs are hard. Usually I add logging and wait for it to happen "
        "again, then look at the logs.",
    ],
    "conflict": [
        "Our staff engineer wanted to build our own job queue; I wanted to use SQS. His "
        "reasoning was that our retry semantics were unusual enough that we'd fight the "
        "abstraction, which was a fair point I hadn't weighted properly. We agreed to "
        "spike both for a week against the actual retry requirements. The spike showed "
        "SQS handled it, and he changed his mind on the evidence. What I took from it "
        "was to convert opinion arguments into decidable ones earlier.",
        "We disagreed about the release process but in the end the manager made the call "
        "and we went with that.",
    ],
    "learning": [
        "I shipped a schema change without a backfill plan and left about 200 thousand "
        "rows with nulls in a column the reporting job assumed was populated. Finance "
        "ran on bad numbers for two days before anyone noticed. The specific thing I'd "
        "change is that I treated 'the migration ran' as done rather than 'the data is "
        "correct'. On the next migration I wrote the verification query before the "
        "migration itself, and I've done that every time since.",
        "I've made mistakes, sure. Mostly I've learned to communicate more and test more.",
    ],
    "fundamentals": [
        "Take a database index. It's usually a B-tree, so lookups walk a shallow tree of "
        "sorted pages rather than scanning. The consequence I've actually hit is that "
        "every index makes writes more expensive, because each insert updates every "
        "tree. We had a table with nine indexes where write latency halved when we "
        "dropped four of them. Where my knowledge stops is the page-splitting details "
        "under heavy concurrent insert — I know it causes fragmentation, I couldn't walk "
        "you through the locking.",
    ],
    "code_judgement": [
        "We had a launch in four days and needed a one-off importer for a single "
        "customer's data. I wrote it as one long script with no tests and a comment at "
        "the top saying it was disposable and why. It ran twice and I deleted it. If "
        "that code had been going into the request path I'd have made the opposite call "
        "— the blast radius is what decides it for me, not how the code looks.",
    ],
}


def scripted_candidate(conductor) -> Callable[[], str]:
    """A `listen` callable that answers whatever the conductor actually asked."""
    used: dict[str, int] = defaultdict(int)

    def listen() -> str:
        question = conductor.current_question
        competency_id = question.competency_id if question else ""
        bank = DEMO_ANSWERS.get(competency_id, [])
        index = used[competency_id]
        used[competency_id] += 1
        return bank[index] if index < len(bank) else NO_MORE

    return listen
