"""Module containing historic widget's assets section processing functions."""

from collections import defaultdict
from urllib.parse import urlsplit

import pandas as pd
from django.template.defaultfilters import floatformat

from api.data import ASA_PROGRAMS
from .constants import DUST_LIMIT, MICROALGOS_TO_ALGOS_RATIO
from .structs import HeaderElement, BodyElement, Total


# # ELEMENTS
class ElementsCreator:
    """Class with methods to convert ledger data into form suitable for rendering.

    :var AsaProducer.ledger_rows: collection of sorted ledger rows
    :type AsaProducer.ledger_rows: list
    :var AsaProducer.columns: column names collection of the sorted assets data
    :type AsaProducer.columns: list
    :var AsaProducer.carrier: instance with storage related methods and variables
    :type AsaProducer.carrier: :class:`storage.main.StorageCarrier`
    """

    ledger_rows = None
    columns = None
    carrier = None

    def __init__(self, ledger_rows, columns, carrier):
        """Set class variables to initial values from provided arguments.

        :param ledger_rows: collection of sorted ledger rows
        :type ledger_rows: list
        :param columns: column names collection of the sorted assets data
        :type columns: list
        :param carrier: instance with storage related methods and variables
        :type carrier: :class:`storage.main.StorageCarrier`
        """
        self.ledger_rows = ledger_rows
        self.columns = columns
        self.carrier = carrier

    def _as_currency(self, value):
        """Return provided value in microAlgos converted to ALGO.

        :param value: provided asset's amount in ALGO
        :type value: int
        :return: str
        """
        return value / MICROALGOS_TO_ALGOS_RATIO

    def _format_amount(self, asset_id, amount):
        """Return provided asset amount in format suitable for rendering.

        :param asset_id: Algorand standard asset identifier
        :type asset_id: int
        :param amount: provided asset's amount in "microunits"
        :type amount: int
        :var decimals: asset's number of digits after decimal point
        :type decimals: int
        :var presentation: truncated asset's number of decimals
        :type presentation: int
        :return: str
        """
        try:
            decimals = self.custom_asa(asset_id).decimals
            presentation = min(4, decimals)
            return floatformat(amount / 10**decimals, f"-{presentation}g")

        except TypeError:
            return ""

    def _format_lp_token(self, lp_token_id):
        """Return formatted name for provided LP token identifier.

        :param lp_token_id: AMM liquidity pool's token identifier
        :type lp_token_id: int
        :var asset1: first asset in liquidity pool
        :type asset1: int
        :var asset2: second asset in liquidity pool
        :type asset2: int
        :var provider: liquidity pool's provider
        :type provider: str
        :var unit1: liquidity pool first asset's unit
        :type unit1: str
        :var unit2: liquidity pool second asset's unit
        :type unit2: str
        :return: two-tuple
        """
        if pd.isna(lp_token_id) or int(lp_token_id) == 0:
            return None

        lp_token_id = int(lp_token_id)
        asset1, asset2, _, provider, url = self.carrier.ledger_pool_info_for_lp_token(
            lp_token_id, capitalize_provider=True
        )

        unit1 = self.custom_asa(asset1).unit
        unit2 = self.custom_asa(asset2).unit
        return (f"{provider} LP {unit1}/{unit2}", url)

    def _is_valid_asset_row(self, asset_id, ledger_row):
        """Return True if provided `row` represents a valid `asset_id` entry.

        :param asset_id: Algorand standard asset identifier
        :type asset_id: int
        :param ledger_row: row of ledger data representing NFT program
        :type ledger_row: tuple
        :return: Boolean
        """
        return (
            True
            if ledger_row[self._row_index("asset")] == asset_id
            and ledger_row[self._row_index("state")] != 0
            and (
                ledger_row[self._row_index("value")] == 0
                or (
                    DUST_LIMIT == 0
                    or abs(ledger_row[self._row_index("value")]) > DUST_LIMIT
                )
            )
            and self.custom_asa(asset_id).name
            else False
        )

    def _nft_amount_from_ledger_row(self, ledger_row):
        """Return NFT amount from provided row of ledger data.

        :param ledger_row: row of ledger data representing NFT program
        :type ledger_row: tuple
        :return: float
        """
        return (
            ledger_row[self._row_index("state")]
            / 10 ** self.custom_asa(ledger_row[self._row_index("asset")]).decimals
        )

    def _nft_item(self, ledger_row, custom_nfts):
        """Return ASA program object created from provided row of ledger data.

        :param ledger_row: row of ledger data representing NFT program
        :type ledger_row: tuple
        :param custom_nfts: NFT collection's custom NFT objects
        :type custom_nfts: list
        :var nft_id: Algorand standard asset identifier
        :type nft_id: int
        :param custom_nft: custom NFT object
        :type custom_nft: :class:`utils.structs.Nft`
        :var program: predefined ASA program instance
        :type program: :class:`api.structs.AsaProgram`
        :return: :class:`widgets.inhouse.historic.structs.BodyElement`
        """
        nft_id = ledger_row[self._row_index("asset")]
        custom_nft = next(
            custom_nft for custom_nft in custom_nfts if custom_nft.id == nft_id
        )
        program = ASA_PROGRAMS.get(ledger_row[self._row_index("code")])
        return BodyElement(
            asset=custom_nft,
            name=_base_program_name(program.name),
            type=program.type,
            url=_base_program_url(program.url),
            source=None,
            amount=self._format_amount(nft_id, ledger_row[self._row_index("state")]),
            value=self._as_currency(ledger_row[self._row_index("value")]),
        )

    def _program_item(self, asset_id, ledger_row):
        """Return body element for `asset_id` created from provided row of ledger data.

        :param asset_id: Algorand standard asset identifier
        :type asset_id: int
        :param ledger_row: row of ledger data representing ASA program
        :type ledger_row: tuple
        :var program: predefined ASA program instance
        :type program: :class:`api.structs.AsaProgram`
        :var source: source LP token name and URL if applicable
        :type source: two-tuple
        :return: :class:`widgets.inhouse.historic.structs.BodyElement`
        """
        program = ASA_PROGRAMS.get(ledger_row[self._row_index("code")])
        source = self._format_lp_token(ledger_row[self._row_index("id")])
        return BodyElement(
            asset=None,
            name=_base_program_name(program.name),
            type=program.type if source is None else None,
            url=_base_program_url(program.url),
            source=source,
            amount=self._format_amount(asset_id, ledger_row[self._row_index("state")]),
            value=self._as_currency(ledger_row[self._row_index("value")]),
        )

    def _row_index(self, column_name):
        """Return index in ledger rows collection for provided column name.

        :param column_name: column name to return index for
        :type column_name: str
        :return: int
        """
        return self.columns.index(column_name)

    def asa_body(self, asset_id):
        """Create and return collection of ASA program objects for provided asset.

        :param asset_id: Algorand standard asset identifier
        :type asset_id: int
        :return: list
        """
        return [
            self._program_item(asset_id, ledger_row)
            for ledger_row in self.ledger_rows
            if self._is_valid_asset_row(asset_id, ledger_row)
        ]

    def asa_header(self, asset_id, total):
        """Create and return ASA header element for provided asset.

        :param asset_id: Algorand standard asset identifier
        :type asset_id: int
        :param total: total value in ALGO for provided asset
        :type total: float
        :var amount: provided asset's total amount
        :type amount: int
        :return: :class:`widgets.inhouse.historic.structs.HeaderElement`
        """
        amount = sum(
            ledger_row[self._row_index("state")]
            for ledger_row in self.ledger_rows
            if self._is_valid_asset_row(asset_id, ledger_row)
        )
        return HeaderElement(
            icon=self.carrier.asset_icon_path(asset_id),
            label=self.custom_asa(asset_id).unit,
            amount=self._format_amount(asset_id, amount),
            total=self._as_currency(total),
        )

    def custom_asa(self, asset_id):
        """Create and return custom ASA object for provided asset identifier.

        :param asset_id: Algorand standard asset identifier
        :type asset_id: int
        :return: :class:`utils.structs.Asa`
        """
        return self.carrier.asset_info(asset_id)

    def nft_body(self, custom_nfts, nfts):
        """Create and return NFT body section from provided NFT collection data.

        :param custom_nfts: NFT collection's custom NFT objects
        :type custom_nfts: list
        :param nfts: collection of NFT collection members' IDs
        :type nfts: list
        :return: list
        """
        return [
            self._nft_item(row, custom_nfts)
            for row in self.ledger_rows
            if row[self._row_index("asset")] in nfts
        ]

    def nft_header(self, collection_name, total, nfts):
        """Create and return NFT header element from provided NFT collection data.

        :param collection_name: currently processed NFT collection name
        :type collection_name: str
        :param total: total value in ALGO for provided NFT collection
        :type total: float
        :var nfts: collection of NFT collection members' IDs
        :type nfts: list
        :var amount: total number of NFTs in provided NFT collection
        :type amount: int
        :return: :class:`widgets.inhouse.historic.structs.HeaderElement`
        """
        amount = sum(
            self._nft_amount_from_ledger_row(row)
            for row in self.ledger_rows
            if row[self._row_index("asset")] in nfts
        )
        return HeaderElement(
            icon=None,
            label=collection_name,
            amount=floatformat(amount, "-2"),
            total=self._as_currency(total),
        )


# # HELPERS
def _base_program_name(name):
    """Return provided name without formatting elements.

    :param name: program's name
    :type name: str
    :return: str
    """
    return (
        name.replace("{0}", "").replace("  ", " ").split("#")[0].strip() if name else ""
    )


def _base_program_url(url):
    """Return provided URL with path part truncated.

    FIXME: change ASA_PROGRAMS items' urls with {0}

    :param url: program's URL
    :type url: str
    :return: str
    """
    return "://".join(urlsplit(url)[:2]) if url else ""


def _group_asset_totals_into_sections(asset_totals, carrier):
    """Filter and return ASA, NFT and not-evaluated sections from provided asset totals.

    :param asset_totals: collection of all asset IDs and related totals
    :type asset_totals: dict
    :var not_eval_totals: collection of not evaluated asset IDs
    :type not_eval_totals: dict
    :var asa_totals: collection of ASA IDs and related totals
    :type asa_totals: dict
    :var nft_totals: collection of NFT IDs and related totals
    :type nft_totals: dict
    :return: tuple
    """
    not_eval_totals = {
        asset_id: value for asset_id, value in asset_totals.items() if value == 0
    }
    asa_totals, nft_totals = carrier.filter_nfts_from_assets(
        {asset_id: value for asset_id, value in asset_totals.items() if value}
    )
    return asa_totals, nft_totals, not_eval_totals


def _group_nfts_by_collection(nft_totals, carrier):
    """Return custom NFT objects, NFT IDs, and totals grouped by collection names.

    :param nft_totals: collection of NFT IDs and related totals
    :type nft_totals: dict
    :param carrier: instance with storage related methods and variables
    :type carrier: :class:`storage.main.StorageCarrier`
    :var nft_data: collection of NFT IDs and related custom NFT data
    :type nft_data: dict
    :var nft_collections: collection of NFT collection names and members' custom NFT data
    :type nft_collections: dict
    :var nft_collection_nfts: collection of NFT collection names and members' IDs
    :type nft_collection_nfts: dict
    :var nft_collection_totals: collection of NFT collection names and related totals
    :type nft_collection_totals: dict
    :var nft_id: currently processed Algorand standard asset identifier
    :type nft_id: int
    :var custom_nft: currently processed custom NFT object
    :type custom_nft: :class:`utils.structs.Nft`
    :return: tuple
    """
    nft_data = carrier.nft_data_for_assets(nft_totals)
    nft_collections = defaultdict(list)
    nft_collection_nfts = defaultdict(list)
    nft_collection_totals = defaultdict(float)
    for nft_id, custom_nft in nft_data.items():
        collection = custom_nft.collection if custom_nft is not None else "others"
        nft_collections[collection].append(custom_nft)
        nft_collection_nfts[collection].append(nft_id)
        nft_collection_totals[collection] += nft_totals.get(nft_id)

    return (
        {
            name: sorted(
                custom_nfts, key=lambda item: nft_totals[item.id], reverse=True
            )
            for name, custom_nfts in sorted(
                nft_collections.items(),
                key=lambda item: nft_collection_totals[item[0]],
                reverse=True,
            )
        },
        nft_collection_nfts,
        nft_collection_totals,
    )


def _sorted_timestamp_data_and_totals_mapping(timestamp_data):
    """Return sorted `timestamp_data` and collection of asset IDs with related totals.

    :param timestamp_data: fully evaluated bundle ledger data for single timestamp
    :type timestamp_data: :class:`pandas.DataFrame`
    :var asset_total_value: collection of assets and related totals
    :type asset_total_value: :class:`pandas.DataFrame`
    :var sorted_ledger: timestamp data sorted by asset totals and asset values
    :type sorted_ledger: :class:`pandas.DataFrame`
    :var asset_totals_mapping: collection of asset IDs and related totals.
    :type asset_totals_mapping: dict
    :return: two-tuple
    """
    asset_total_value = timestamp_data.groupby("asset")["value"].sum()
    timestamp_data["asset_total"] = timestamp_data["asset"].map(asset_total_value)
    sorted_ledger = timestamp_data.sort_values(
        by=["asset_total", "value"], ascending=[False, False]
    )
    asset_totals_mapping = {
        int(asset_id): value
        for asset_id, value in sorted(
            asset_total_value.to_dict().items(), key=lambda x: x[1], reverse=True
        )
    }
    return sorted_ledger.drop(columns="asset_total"), asset_totals_mapping


# # PROCESS
def _create_asa_section(asa_totals, elements_creator):
    """Create and return ASA section from provided totals and UI creator instance.

    :param asa_totals: collection of ASA IDs and related totals
    :type asa_totals: dict
    :param elements_creator: instance holding UI elements creation methods
    :type elements_creator: :class:`ElementsCreator`
    :var asset_id: currently processed Algorand standard asset identifier
    :type asset_id: int
    :var total: total value in ALGO for currently processed asset
    :type total: float
    :return: dict
    """
    return [
        {
            "info": elements_creator.custom_asa(asset_id),
            "header": elements_creator.asa_header(asset_id, total),
            "body": elements_creator.asa_body(asset_id),
        }
        for asset_id, total in asa_totals.items()
    ]


def _create_nft_section(nft_totals, elements_creator):
    """Create and return NFT section from provided totals and UI creator instance.

    :param nft_totals: collection of NFT IDs and related totals
    :type nft_totals: dict
    :param elements_creator: instance holding UI elements creation methods
    :type elements_creator: :class:`ElementsCreator`
    :var nft_collections: collection of NFT collection names and members' custom NFT data
    :type nft_collections: dict
    :var nft_collection_nfts: collection of NFT collection names and members' IDs
    :type nft_collection_nfts: dict
    :var nft_collection_totals: collection of NFT collection names and related totals
    :type nft_collection_totals: dict
    :var collection_name: currently processed NFT collection name
    :type collection_name: str
    :var custom_nfts: currently processed NFT collection's custom NFT objects
    :type custom_nfts: list
    :return: dict
    """
    nft_collections, nft_collection_nfts, nft_collection_totals = (
        _group_nfts_by_collection(nft_totals, elements_creator.carrier)
    )
    return [
        {
            "info": collection_name,
            "header": elements_creator.nft_header(
                collection_name,
                nft_collection_totals.get(collection_name),
                nft_collection_nfts.get(collection_name),
            ),
            "body": elements_creator.nft_body(
                custom_nfts, nft_collection_nfts.get(collection_name)
            ),
        }
        for collection_name, custom_nfts in nft_collections.items()
    ]


def _create_noteval_section(asa_totals, elements_creator):
    """Create and return not-evaluated section from provided arguments.

    :param asa_totals: collection of ASA IDs and related zero totals
    :type asa_totals: dict
    :param elements_creator: instance holding UI elements creation methods
    :type elements_creator: :class:`ElementsCreator`
    :var section: not-evaluated section's items collection
    :type section: list
    :var asset_id: currently processed Algorand standard asset identifier
    :type asset_id: int
    :var info: currently processed asset's custom ASA instance
    :type info: :class:`utils.structs.Asa`
    :var body: currently processed asset's programs collection
    :type body: list
    :return: dict
    """
    section = []
    for asset_id in asa_totals:
        info = elements_creator.custom_asa(asset_id)
        body = elements_creator.asa_body(asset_id)
        if info.name and body:
            section.append({"info": info, "body": body})

    return section


def _create_total(asa_totals, nft_totals, usd_price_in_algo):
    """Create and return total collection from provided arguments.

    :param asa_totals: collection of ASA IDs and related totals
    :type asa_totals: dict
    :param nft_totals: collection of NFT IDs and related totals
    :type nft_totals: dict
    :param usd_price_in_algo: ALGO price in USDC for provided timestamp
    :type usd_price_in_algo: float
    :var algo: ALGO amount
    :type algo: int
    :var asasum: total ASA value in ALGO
    :type asasum: int
    :var nftsum: total ASA value in ALGO
    :type nftsum: int
    :return: :class:`widgets.inhouse.historic.structs.Total`
    """
    algo = asa_totals.get(0, 0) / MICROALGOS_TO_ALGOS_RATIO
    asasum = sum(asa_totals.values()) / MICROALGOS_TO_ALGOS_RATIO - algo
    nftsum = sum(nft_totals.values()) / MICROALGOS_TO_ALGOS_RATIO
    return Total(
        algo,
        asasum,
        nftsum,
        algo + asasum + nftsum,
        (algo + asasum + nftsum) / usd_price_in_algo,
        usd_price_in_algo,
        1 / usd_price_in_algo,
    )


def _process_sorted_ledger(sorted_ledger, asset_totals, usd_price_in_algo, carrier):
    """Filter and return ASA, NFT and not-evaluated sections from provided asset totals.

    :param sorted_ledger: timestamp data sorted by asset totals and asset values
    :type sorted_ledger: :class:`pandas.DataFrame`
    :param asset_totals: collection of asset IDs and related totals.
    :type asset_totals: dict
    :param usd_price_in_algo: ALGO price in USDC for provided timestamp
    :type usd_price_in_algo: float
    :param carrier: instance with storage related methods and variables
    :type carrier: :class:`storage.main.StorageCarrier`
    :var ledger_rows: collection of sorted ledger rows
    :type ledger_rows: list
    :var columns: column names collection of the sorted assets data
    :type columns: list
    :var asa_totals: collection of ASA IDs and related totals
    :type asa_totals: dict
    :var nft_totals: collection of NFT IDs and related totals
    :type nft_totals: dict
    :var not_eval_totals: collection of not evaluated asset IDs
    :type not_eval_totals: dict
    :var elements_creator: instance holding UI elements creation methods
    :type elements_creator: :class:`ElementsCreator`
    :return: dict
    """
    ledger_rows = list(sorted_ledger.itertuples(index=False, name=None))
    columns = sorted_ledger.columns.tolist()
    asa_totals, nft_totals, not_eval_totals = _group_asset_totals_into_sections(
        asset_totals, carrier
    )
    elements_creator = ElementsCreator(ledger_rows, columns, carrier)
    return {
        "total": _create_total(asa_totals, nft_totals, usd_price_in_algo),
        "asa": _create_asa_section(asa_totals, elements_creator),
        "nft": _create_nft_section(nft_totals, elements_creator),
        "noteval": _create_noteval_section(not_eval_totals, elements_creator),
    }


def assets_data_from_timestamp_data(timestamp, timestamp_data, carrier):
    """Create ready-for-rendering data from provided single-timestamp ledger dataframe.

    :param timestamp: seconds since epoch data is processed for
    :type timestamp: int
    :param timestamp_data: fully evaluated bundle ledger data for single timestamp
    :type timestamp_data: :class:`pandas.DataFrame`
    :param carrier: instance with storage related methods and variables
    :type carrier: :class:`storage.main.StorageCarrier`
    :var sorted_ledger: timestamp data sorted by asset totals and asset values
    :type sorted_ledger: :class:`pandas.DataFrame`
    :var asset_totals_mapping: collection of asset IDs and related totals
    :type asset_totals_mapping: dict
    :var usd_price_in_algo: ALGO price in USDC for provided timestamp
    :type usd_price_in_algo: float
    :return: dict
    """
    sorted_ledger, asset_totals_mapping = _sorted_timestamp_data_and_totals_mapping(
        timestamp_data
    )
    usd_price_in_algo = carrier.usd_price_in_algo_for_timestamp(timestamp)
    return _process_sorted_ledger(
        sorted_ledger, asset_totals_mapping, usd_price_in_algo, carrier
    )
