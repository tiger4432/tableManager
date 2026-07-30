import re
import json
import logging
import os
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Declaration schema (the single source of "what may be declared")
# ---------------------------------------------------------------------------
# A key that is not here is REJECTED with a reason rather than ignored, the same
# way ontology_config._unknown_keys does: a typo must not silently disable the
# declaration it was meant to make.
ALLOWED_RULE_KEYS = {"column", "regex", "type", "default", "required"}
ALLOWED_CAST_TYPES = {"str", "int", "float", "bool"}

# ---------------------------------------------------------------------------
# Named reasons. A declared-and-absent extraction is REPORTED, never blank:
# 미상 ≠ 빈칸. Every state below is counted per file and logged.
# ---------------------------------------------------------------------------
# Declared, matched nothing. With one fixed folder structure this never happens;
# with varied structures some files carry the token and some do not, and a run
# where half the files lost a column must not look identical to one where they
# all matched.
REASON_NO_MATCH = "no_match"
# The pattern matched MORE THAN ONE distinct value. Refused, not resolved: there
# is no authority to break the tie, so taking `re.search`'s first hit would be a
# guess written into a data column. Same word as
# enrichment_analysis.CLS_AMBIGUOUS / enrichment_candidates.REASON_AMBIGUOUS —
# one vocabulary for one state, deliberately not a second synonym.
REASON_AMBIGUOUS = "ambiguous_reference"
# Matched, but the declared `type` could not represent the captured text. A
# failed cast used to be stored as None, i.e. as a blank — same silence class.
REASON_CAST_FAILED = "cast_failed"
# PRECEDENCE (user ruling 2026-07-30: "파일이 정본" — the file is authoritative
# over the path). The row carried its own value for a path-derived column, so the
# row won. This is NOT ambiguity: the resolution is settled, only the observation
# was missing. It means either the file sits in the wrong folder or the pattern
# matched the wrong token — both worth knowing, neither worth blocking on.
REASON_FILE_OVERRIDES_PATH = "file_overrides_path"
# A path-derived value was DISCARDED because the file's own header supplied the
# same column (user ruling 2026-07-30: the ruling extends to the header, and the
# path is the WEAKER of the two — merge order `filename < header < row`).
#
# Why this is the one worth naming, and the reverse is not: the header winning IS
# the ruling, so it is the normal, expected outcome and warns about nothing. What
# an operator cannot otherwise see is that the folder rule they declared produced
# a value and then had no effect — silence would read as "the rule never matched".
# So the DISCARD is what gets counted. Never blocking: the resolution is settled,
# only the observation was missing (same shape as REASON_FILE_OVERRIDES_PATH).
REASON_PATH_VALUE_DISCARDED = "path_value_discarded"


class RuleDeclarationError(ValueError):
    """A `rules` / `header_rules` / `filename_rules` declaration is malformed.

    Raised at LOAD time with a named reason, not at parse time as an IndexError.
    A regex without a capture group is a declaration error; letting it reach
    `match.group(1)` turns an operator's typo into a program crash.
    """


def _validate_rules(raw_rules, where: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Validate one rule family. Returns (normalized_rules, error_reasons).

    Every rejection names its reason and its location (`where[i]`) so the message
    identifies the declaration to fix.
    """
    errors: List[str] = []
    if raw_rules is None:
        return [], errors
    if not isinstance(raw_rules, list):
        return [], [f"{where}: must be a list of rule objects, got {type(raw_rules).__name__}"]

    normalized: List[Dict[str, Any]] = []
    seen_columns = set()
    for i, raw in enumerate(raw_rules):
        at = f"{where}[{i}]"
        if not isinstance(raw, dict):
            errors.append(f"{at}: must be an object, got {type(raw).__name__}")
            continue
        unknown = sorted(
            k for k in raw.keys()
            if isinstance(k, str) and not k.startswith("__") and k not in ALLOWED_RULE_KEYS
        )
        if unknown:
            errors.append(
                f"{at}: unknown key(s) {unknown} — allowed: {sorted(ALLOWED_RULE_KEYS)}. "
                "Declarations are rejected rather than ignored so that a typo cannot "
                "silently disable the declaration it was meant to make."
            )
            continue

        column = raw.get("column")
        if not isinstance(column, str) or not column.strip():
            errors.append(f"{at}: 'column' must be a non-empty string")
            continue
        column = column.strip()
        if column in seen_columns:
            errors.append(
                f"{at}: column '{column}' is declared twice in {where} — the second "
                "declaration would silently overwrite the first"
            )
            continue

        pattern = raw.get("regex")
        if not isinstance(pattern, str) or not pattern:
            errors.append(f"{at}: 'regex' must be a non-empty string")
            continue
        try:
            compiled = re.compile(pattern)
        except re.error as e:
            errors.append(f"{at}: 'regex' does not compile — {e}")
            continue
        if compiled.groups < 1:
            errors.append(
                f"{at}: 'regex' {pattern!r} has no capture group. The extracted value is "
                "group(1), so a group-less pattern can never yield a value — write the "
                "part to capture in parentheses, e.g. '(LOT-\\\\d+)' instead of 'LOT-\\\\d+'."
            )
            continue

        cast_type = raw.get("type", "str")
        if cast_type not in ALLOWED_CAST_TYPES:
            errors.append(
                f"{at}: unknown type {cast_type!r} — allowed: {sorted(ALLOWED_CAST_TYPES)}"
            )
            continue

        required = raw.get("required", False)
        if not isinstance(required, bool):
            errors.append(f"{at}: 'required' must be a boolean (default false)")
            continue

        seen_columns.add(column)
        normalized.append({
            "column": column,
            "regex": pattern,
            "compiled": compiled,
            "type": cast_type,
            "default": raw.get("default"),
            # Defaults to False so an existing declaration that omits it keeps
            # today's behaviour exactly.
            "required": required,
        })
    return normalized, errors


class AdvancedIngester:
    """
    통합 인제스터: 정규표현식 기반의 범용 파싱 기능과
    헤더 메타데이터 추출 기능을 하나의 클래스로 제공합니다.

    Declarations are validated when the config is READ (`RuleDeclarationError`),
    and every extraction that a declaration asked for but could not produce is
    reported — see the REASON_* constants above and `issues` on the extraction
    methods.
    """
    def __init__(self, config_path: str, server_url: str = "http://127.0.0.1:8000"):
        self.config = self._load_json(config_path)
        self.server_url = server_url
        self.config_path = config_path

        self.table_name = self.config.get("table_name")
        self.source_name = self.config.get("source_name", "advanced_ingester")
        self.updated_by = self.config.get("updated_by", "agent_adv")
        self.business_key_col = self.config.get("business_key_column", "id")

        # 고급 규칙 (Advanced)
        self.table_start_pattern = self.config.get("table_start_pattern", "")
        self.table_end_pattern = self.config.get("table_end_pattern", "")

        # Validate all three rule families with the same schema and fail at load
        # with the full list of named reasons — an operator fixes one config pass,
        # not one error per restart.
        errors: List[str] = []
        self.rules, errs = _validate_rules(self.config.get("rules"), "rules")
        errors.extend(errs)
        self.header_rules, errs = _validate_rules(self.config.get("header_rules"), "header_rules")
        errors.extend(errs)
        self.filename_rules, errs = _validate_rules(
            self.config.get("filename_rules"), "filename_rules"
        )
        errors.extend(errs)
        if errors:
            raise RuleDeclarationError(
                f"{config_path}: invalid rule declaration(s):\n  - "
                + "\n  - ".join(errors)
            )

        # Precedence overlap, computed ONCE per ingester (not per row): the set of
        # path-derived columns that some other declaration can also produce. Empty
        # in the normal case, which is what keeps the per-row conflict check free.
        filename_cols = {r["column"] for r in self.filename_rules}
        row_cols = {r["column"] for r in self.rules}
        header_cols = {r["column"] for r in self.header_rules}
        self._row_overlap = filename_cols & row_cols
        self._header_overlap = filename_cols & header_cols
        # Columns that MORE THAN ONE source can produce. `_merge_row` needs the
        # fill pass only for these, and this set is empty in the normal case —
        # which is what keeps the per-row merge cost at today's level.
        self._fill_merge_cols = (
            self._row_overlap | self._header_overlap | (header_cols & row_cols)
        )
        for col in sorted(self._row_overlap):
            logger.info(
                f"[{self.source_name}] column '{col}' is declared in BOTH filename_rules and "
                "rules — the file is authoritative (ruling 2026-07-30 '파일이 정본'), so the "
                "path value fills the column only where the row does not carry one. "
                f"Disagreements are counted as '{REASON_FILE_OVERRIDES_PATH}'."
            )
        for col in sorted(self._header_overlap):
            # INFO, not WARNING: after the 2026-07-30 ruling the header winning is
            # the DESIGNED outcome, not a surprise. Warning about the normal case
            # is how a log stops being read.
            logger.info(
                f"[{self.source_name}] column '{col}' is declared in BOTH filename_rules and "
                "header_rules — the file is authoritative (ruling 2026-07-30 '파일이 정본'), so "
                "the header wins and the path value fills the column only where the header "
                f"does not carry one. Discards are counted as '{REASON_PATH_VALUE_DISCARDED}'."
            )

    def _load_json(self, path: str) -> Dict:
        if not os.path.exists(path):
            if not os.path.isabs(path):
                alt_path = os.path.join(os.path.dirname(__file__), path)
                if os.path.exists(alt_path): path = alt_path
                else: raise FileNotFoundError(f"Config not found: {path}")
            else: raise FileNotFoundError(f"Config not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _cast_type(self, value: str, target_type: str) -> Any:
        try:
            if target_type == "int": return int(value)
            if target_type == "float": return float(value)
            if target_type == "bool": return value.lower() in ("true", "1", "yes")
            return str(value)
        except: return None

    @staticmethod
    def _record(issues: Optional[list], **fields) -> dict:
        """Append one named observation to the optional collector and return it.

        Same shape as ontology_config._record: the return value is identical
        whether or not a collector was passed, so callers that want none pay
        nothing.
        """
        if issues is not None:
            issues.append(fields)
        return fields

    def extract_header_metadata(self, lines: List[str]) -> Dict[str, Any]:
        """헤더 영역에서 메타데이터를 추출합니다."""
        metadata = {}
        if not self.header_rules: return metadata

        for line in lines:
            if self.table_start_pattern and re.search(self.table_start_pattern, line):
                break
            for rule in self.header_rules:
                match = rule["compiled"].search(line)
                if match:
                    val = match.group(1)
                    metadata[rule["column"]] = self._cast_type(val, rule.get("type", "str"))
        return metadata

    def extract_path_metadata(
        self, subject: str, issues: Optional[list] = None
    ) -> Tuple[Dict[str, Any], Optional[dict]]:
        """Extract declared columns from a source PATH. Returns (data, refusal).

        `subject` is the path relative to the ingestion root, POSIX-separated
        (`directory_watcher.relative_source_path` produces exactly this), e.g.
        "batchA/sub2/user(kim)x.csv". A bare filename is the degenerate case with
        zero directories, which is why the declaration key is still
        `filename_rules`: it is one mechanism over one subject, not two channels
        for the same string.

        The folder names are information — lot, equipment, date — and they reach
        the declaration as themselves. "/" cannot occur inside a directory name,
        so a component-shaped pattern like `([^/]+)/` is unambiguous with no
        invented separator and no sanitizing.

        `refusal` is None unless a rule declared `required: true` could not
        produce a trustworthy value; in that case the caller must yield NO rows
        for this file (the refusal names the column and the reason).

        Patterns are value-shaped and position-independent (`re.search`
        semantics), which is what makes them usable against folder structures
        that vary between drops. NOTE: a pattern anchored with `^` against a bare
        filename does NOT survive the widening to a path — value-shaped patterns
        do. Every rule that asked for a value and did not get one is recorded.
        """
        filename = subject
        data: Dict[str, Any] = {}
        refusal = None
        for rule in self.filename_rules:
            col = rule["column"]
            # finditer, not search: the FIRST match is only the right answer when
            # it is the ONLY answer. Distinct values, so a token repeated
            # identically (e.g. the same lot in two path levels) is not ambiguity.
            found = []
            for m in rule["compiled"].finditer(filename):
                v = m.group(1)
                if v not in found:
                    found.append(v)

            if not found:
                issue = self._record(
                    issues, scope="filename_rules", column=col,
                    reason=REASON_NO_MATCH, filename=filename,
                    regex=rule["regex"], required=rule["required"],
                )
            elif len(found) > 1:
                issue = self._record(
                    issues, scope="filename_rules", column=col,
                    reason=REASON_AMBIGUOUS, filename=filename,
                    regex=rule["regex"], values=list(found),
                    required=rule["required"],
                )
            else:
                val = self._cast_type(found[0], rule["type"])
                if val is None:
                    issue = self._record(
                        issues, scope="filename_rules", column=col,
                        reason=REASON_CAST_FAILED, filename=filename,
                        regex=rule["regex"], raw_value=found[0],
                        type=rule["type"], required=rule["required"],
                    )
                else:
                    data[col] = val
                    continue

            logger.warning(
                f"[{self.source_name}] filename_rules '{col}' → {issue['reason']} "
                f"for {filename!r}"
                + (f" (values={issue['values']})" if "values" in issue else "")
            )
            if rule["required"] and refusal is None:
                refusal = issue
        return data, refusal

    def parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        """정규표현식 규칙에 따라 한 줄을 파싱합니다."""
        extracted = {}
        found_any = False
        for rule in self.rules:
            col = rule["column"]
            match = rule["compiled"].search(line)
            if match:
                val = self._cast_type(match.group(1), rule.get("type", "str"))
                if val is not None:
                    extracted[col] = val
                    found_any = True
                else: extracted[col] = rule.get("default")
            else: extracted[col] = rule.get("default")

            if rule.get("required") and (extracted.get(col) is None):
                return None
        return extracted if found_any else None

    def _merge_row(self, header_metadata: dict, filename_data: dict, row_data: dict) -> dict:
        """Merge the three metadata sources into one row.

        PRECEDENCE IS A RULING, NOT AN ARTEFACT OF DICT ORDER (2026-07-30,
        "파일이 정본" — the file is authoritative over the path):

            filename_data  <  header_metadata  <  row_data

        THE PATH IS THE WEAKEST OF THE THREE, and that is the whole ruling. A
        value written INSIDE the file is what that file itself asserts; a folder
        name is external context that changes the moment someone moves the file.
        So "파일이 정본" covers the header too, and between a header and a path the
        path is the weaker claim. The path-derived value FILLS a column no
        in-file source carries; wherever the file speaks — header or row — the
        file wins.

        Do NOT reorder these three without a new ruling. Putting `filename_data`
        after `header_metadata` again would make a file's filing LOCATION
        override the file's own contents, which is the inversion this ruling
        exists to forbid. `test_merge_order_is_the_declared_ruling` pins both
        directions.

        A SOURCE WINS ONLY WHERE IT ACTUALLY CARRIES A VALUE. `parse_line` emits
        EVERY declared column on every row, using `default` (usually None) for the
        rules that did not match — so a plain `{**a, **b, **c}` lets a row that is
        SILENT about a column write a None over the path- or header-derived value,
        and the fill half of the ruling never happens. None is `parse_line`'s
        absence marker, not a value: 미상 ≠ 빈칸. A declared non-None `default` IS
        a value the declaration provides, so it still wins.

        Cost: the fill pass runs only over `_fill_merge_cols` (columns more than
        one source can produce), which is empty unless the same column is declared
        in two families — so the common path is exactly today's dict merge.
        """
        merged = {**filename_data, **header_metadata, **row_data}
        for col in self._fill_merge_cols:
            if merged.get(col) is not None:
                continue
            # Fill in DESCENDING precedence — the strongest source that actually
            # carries a value wins the fill too, or the fill would quietly
            # contradict the order above. Note this is also what rescues a header
            # CAST FAILURE: `extract_header_metadata` stores None for a rule whose
            # cast failed, and that None now sits ABOVE the path value in the dict
            # merge. Without this pass a bad `type:` on a header rule would blank a
            # perfectly good path value — a silent loss, not a visible one.
            fill = header_metadata.get(col)
            if fill is None:
                fill = filename_data.get(col)
            if fill is not None:
                merged[col] = fill
        return merged

    def process_file(self, file_path: str, rel_path: Optional[str] = None,
                     issues: Optional[list] = None) -> List[Dict[str, Any]]:
        """파일 전체를 스캔하여 파싱된 행 리스트를 반환합니다.

        rel_path: the source path relative to the ingestion root, POSIX-separated
        — what `filename_rules` matches against. A pipeline script running under
        the directory watcher gets it as `self.rel_path`. Omitted (None) falls
        back to `basename(file_path)`, which is exactly the previous behaviour, so
        an existing caller is unchanged.

        issues: optional collector of named observations (REASON_* above). The
        return value is the same with or without it; the collector exists so a
        caller can surface "this run lost a column on N files" instead of
        shipping blanks.
        """
        if not os.path.exists(file_path): return []

        with open(file_path, "r", encoding="utf-8") as f:
            all_lines = f.readlines()

        header_metadata = self.extract_header_metadata(all_lines)

        filename = rel_path or os.path.basename(file_path)
        filename_data, refusal = self.extract_path_metadata(filename, issues=issues)
        if refusal is not None:
            logger.warning(
                f"[{self.source_name}] file refused: required filename_rules column "
                f"'{refusal['column']}' → {refusal['reason']} for {filename!r} — 0 rows "
                "ingested (a row without it is not trustworthy)."
            )
            return []

        # The path value was produced and then DISCARDED because the header
        # supplied the same column. Counted so an operator who declared a folder
        # rule and sees no effect knows why. Only the overlapping columns are
        # inspected, and the overlap is empty in the normal case.
        #
        # `is not None` on the header side is load-bearing: a header rule whose
        # cast failed stores None, and `_merge_row`'s fill pass then restores the
        # PATH value — so recording a discard there would report a loss that did
        # not happen.
        for col in self._header_overlap:
            if col in filename_data and header_metadata.get(col) is not None \
                    and header_metadata[col] != filename_data[col]:
                self._record(
                    issues, scope="filename_rules", column=col,
                    reason=REASON_PATH_VALUE_DISCARDED, filename=filename,
                    path_value=filename_data[col], header_value=header_metadata[col],
                )

        parsed_rows = []
        in_table = not bool(self.table_start_pattern) # 패턴 없으면 즉시 시작
        # Counted, never blocking (the row wins by ruling). Counts rather than
        # per-row records so the memory cost is O(overlap), not O(rows).
        row_conflicts: Dict[str, dict] = {}

        for line in all_lines:
            line = line.strip()
            if not line: continue

            if not in_table:
                if re.search(self.table_start_pattern, line):
                    in_table = True
                continue

            if self.table_end_pattern and re.search(self.table_end_pattern, line):
                break

            row_data = self.parse_line(line)
            if row_data:
                for col in self._row_overlap:
                    if col in filename_data and row_data.get(col) is not None \
                            and row_data[col] != filename_data[col]:
                        seen = row_conflicts.setdefault(
                            col, {"count": 0, "path_value": filename_data[col],
                                  "example_row_value": row_data[col]}
                        )
                        seen["count"] += 1
                parsed_rows.append(self._merge_row(header_metadata, filename_data, row_data))

        for col, info in row_conflicts.items():
            logger.warning(
                f"[{self.source_name}] '{col}': {info['count']} row(s) disagree with the "
                f"path-derived value {info['path_value']!r} (e.g. {info['example_row_value']!r}) "
                f"in {filename!r} — the file wins by ruling; check whether the file is filed "
                "in the wrong folder or the pattern matched the wrong token."
            )
            self._record(
                issues, scope="filename_rules", column=col,
                reason=REASON_FILE_OVERRIDES_PATH, filename=filename, **info,
            )

        return parsed_rows
