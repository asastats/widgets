"""Rebuild the engine's keyed assets payload into the display namedtuples that
``utils.charts`` (shared with the live portfolio view) and ``assets.html``
expect. Inverse of the engine's ``to_wire``; the keyed wire is the contract.
"""

from utils.structs import Asa, BodyElement, HeaderElement, Nft, Total


def _build(named_tuple, data):
    """Build ``named_tuple`` from ``data`` by field name.

    Tolerant by design: keys missing from ``data`` become ``None`` (absorbs the
    engine omitting ``Total.noteval``); keys present in ``data`` but not on the
    type are ignored (absorbs the engine adding a field later).

    :param named_tuple: the target namedtuple class
    :param data: keyed dict from the engine
    :return: instance of ``named_tuple``
    """
    return named_tuple(**{field: data.get(field) for field in named_tuple._fields})


def _body(rows):
    """Rebuild a list of body rows into ``BodyElement`` instances.

    ASA/noteval rows carry ``asset=None``; NFT rows carry a nested
    ``utils.structs.Nft`` which ``to_wire`` flattened to a dict, so restore it.

    :param rows: list of keyed body-row dicts (or None)
    :return: list
    """
    elements = []
    for row in rows or []:
        element = _build(BodyElement, row)
        if isinstance(element.asset, dict):  # NFT row -> rebuild the nested Nft
            element = element._replace(asset=_build(Nft, element.asset))
        elements.append(element)

    return elements


def deserialize_assets_data(data):
    """Rebuild a full assets-data payload into display namedtuples.

    :param data: keyed payload from the engine (``response.json()["data"]``)
    :return: dict with the same section keys, values rebuilt into namedtuples
    """
    rebuilt = dict(data)
    if isinstance(data.get("total"), dict):
        rebuilt["total"] = _build(Total, data["total"])

    rebuilt["asa"] = [
        {
            **item,
            "info": _build(Asa, item["info"]),
            "header": _build(HeaderElement, item["header"]),
            "body": _body(item.get("body")),
        }
        for item in data.get("asa", [])
    ]
    rebuilt["nft"] = [
        {
            **item,  # NFT "info" is the collection name (a string) -- leave as-is
            "header": _build(HeaderElement, item["header"]),
            "body": _body(
                item.get("body")
            ),  # NFT rows are BodyElement; _body rebuilds nested Nft
        }
        for item in data.get("nft", [])
    ]
    rebuilt["noteval"] = [
        {
            **item,
            "info": _build(Asa, item["info"]),
            "body": _body(item.get("body")),  # noteval items carry no "header"
        }
        for item in data.get("noteval", [])
    ]
    return rebuilt
