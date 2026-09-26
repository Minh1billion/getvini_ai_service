import logging
from typing import Optional

import structural

from app.common.upload import SPREADSHEET_EXTS
from app.core.config import DICTIONARIES_DIR
from app.domain.sheet_structure.scenario import scan_sheet, scan_sheet_units
from app.infra.sheet_reader import read_merges, read_sheet, resolve_sheet_names

logger = logging.getLogger("spellcheck.service")

_DICTIONARIES = {"en": "en_words.txt", "vi": "vi_words.txt"}
_LANG_SETS = {"en": ["en"], "vi": ["vi"]}
_ALL_SETS = ["en", "vi"]


def register_dictionaries():
    for name, filename in _DICTIONARIES.items():
        structural.register_set(name, str(DICTIONARIES_DIR / filename))


def parse_whitelist(raw: Optional[str]) -> set:
    return {w.strip() for w in raw.split(",")} if raw else set()


def is_error(token: str, whitelist, lang: str) -> bool:
    if token in whitelist:
        return False
    return not structural.contains_any(token, _LANG_SETS.get(lang, _ALL_SETS), True)


def check_unit(unit: dict, whitelist, lang: str):
    errors = []
    for token in structural.tokenize(unit["text"]):
        for sub, tag in structural.tag(token):
            if tag != "WORD":
                continue
            if is_error(sub, whitelist, lang):
                errors.append({
                    "location": unit["location"],
                    "token": sub,
                    "sheet": unit.get("sheet"),
                    "scenario": unit.get("scenario"),
                    "scenarioId": unit.get("scenarioId"),
                })
    return errors


def extract_units(path: str, ext: str, sheet_names: Optional[str], scenario_ids: Optional[set] = None):
    units = []
    scanned_scenarios = []
    if ext in SPREADSHEET_EXTS:
        selected_sheets = resolve_sheet_names(path, sheet_names)
        multi = len(selected_sheets) > 1
        for sheet in selected_sheets:
            rows = read_sheet(path, sheet)
            merges = read_merges(path, sheet)
            sheet_blocks = scan_sheet(sheet, rows, merges)
            scanned_scenarios.extend(sheet_blocks)

            sheet_scenario_ids = None
            if scenario_ids is not None:
                sheet_scenario_ids = {sid for sid in scenario_ids if sid.startswith(f"{sheet}::")}
                if sheet_blocks and not sheet_scenario_ids:
                    # Sheet has scenarios but none of them were selected -> don't scan this sheet
                    continue
                if not sheet_blocks:
                    # Sheet has no scenario markup at all -> nothing to restrict by, scan it whole
                    sheet_scenario_ids = None

            units.extend(scan_sheet_units(sheet, rows, multi, blocks=sheet_blocks, scenario_ids=sheet_scenario_ids))
        logger.info(
            "[SHEET_DEBUG] extract_units requested_sheet_names=%s resolved_sheets=%s scenario_ids=%s total_units=%s",
            sheet_names, selected_sheets, scenario_ids, len(units),
        )
    else:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f):
                line = line.rstrip("\n")
                if line.strip():
                    units.append({"location": f"L{i + 1}", "text": line, "sheet": None, "scenario": None, "scenarioId": None})
    return units, scanned_scenarios
