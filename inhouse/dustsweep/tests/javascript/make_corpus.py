"""Build the transaction corpus the property tests draw from.

**Why a generated corpus rather than arbitrary bytes.** `dustsweep.test.js`
states the rule this follows: every fixture is produced by algosdk's own
encoder, because the decoder is being tested against Algorand's canonical
msgpack and a hand-rolled fixture would only test it against someone's idea of
that. A fast-check generator emitting msgpack directly would have exactly that
problem.

So the *transactions* are real and the *combinations* are fuzzed: fast-check
draws groups from this corpus and pairs them with arbitrary descriptions, which
is where the interesting failures live -- `S2` was a relationship between the
bytes and the description, not a malformed transaction.

Run from this directory with a python that has algosdk:

    python make_corpus.py > corpus.json
"""

import json
import sys

from algosdk import encoding
from algosdk.transaction import (
    AssetTransferTxn,
    PaymentTxn,
    SuggestedParams,
    assign_group_id,
)

OWNER = "OGRUNXPSMO7Z7EGOGONA7BVEIN7YIJZZB372GZGJIAPB363C6KB42CEN2M"
CREATOR = "2EVGZ4BGOSL3J64UYDE2BUGTNTBZZZLI54VUQQNZZLYCDODLY33UGXNSIU"
STRANGER = "B35TU5Q2VOXPL2AIRLKZP2GI65EIVZCRZLK6KBZVPXZJ3DVJQVJMIIXPZU"
GENESIS = "wGHE2Pwdvd7S12BL5FaOP20EGYesN73ktiC1qzkkit8="

EMPTY_ASSET = 5
FORFEIT_ASSET = 9
UNLISTED_ASSET = 999


def params(fee=1000):
    return SuggestedParams(
        fee=fee, first=1, last=1001, gh=GENESIS, flat_fee=True, min_fee=1000
    )


def axfer(**overrides):
    fields = {
        "sender": OWNER,
        "sp": params(overrides.pop("fee", 1000)),
        "receiver": OWNER,
        "amt": 0,
        "index": EMPTY_ASSET,
        "close_assets_to": OWNER,
    }
    fields.update(overrides)
    return encoding.msgpack_encode(assign_group_id([AssetTransferTxn(**fields)])[0])


def pay(**overrides):
    fields = {
        "sender": OWNER,
        "sp": params(overrides.pop("fee", 1000)),
        "receiver": OWNER,
        "amt": 0,
    }
    fields.update(overrides)
    return encoding.msgpack_encode(assign_group_id([PaymentTxn(**fields)])[0])


#: Each entry is `(name, base64, what makes it interesting)`. The names are
#: what a failing property prints, so they say what the transaction is.
CORPUS = {
    # the two shapes an honest sweep produces
    "empty_close_to_self": axfer(),
    "forfeit_to_creator": axfer(index=FORFEIT_ASSET, close_assets_to=CREATOR),
    # every rule closeOutProblems has, one transaction each
    "payment": pay(),
    "payment_draining_algo": pay(close_remainder_to=STRANGER),
    "rekey": axfer(rekey_to=STRANGER),
    "with_amount": axfer(amt=7, close_assets_to=CREATOR, index=FORFEIT_ASSET),
    "no_close": axfer(close_assets_to=None),
    "sent_by_a_stranger": axfer(sender=STRANGER),
    "paying_a_stranger": axfer(receiver=STRANGER),
    "closing_to_a_stranger": axfer(close_assets_to=STRANGER),
    "unlisted_asset": axfer(index=UNLISTED_ASSET),
    # fees, for S3
    "zero_fee": axfer(fee=0),
    "fee_at_the_limit": axfer(fee=10_000),
    "fee_over_the_limit": axfer(fee=10_001),
    "fee_of_five_algo": axfer(fee=5_000_000),
    # a forfeit to somebody who is not the creator, for S2
    "forfeit_to_a_stranger": axfer(
        index=FORFEIT_ASSET, close_assets_to=STRANGER
    ),
}

json.dump(
    {
        "owner": OWNER,
        "creator": CREATOR,
        "stranger": STRANGER,
        "emptyAsset": EMPTY_ASSET,
        "forfeitAsset": FORFEIT_ASSET,
        "unlistedAsset": UNLISTED_ASSET,
        "transactions": CORPUS,
    },
    sys.stdout,
    indent=2,
    sort_keys=True,
)
sys.stdout.write("\n")
