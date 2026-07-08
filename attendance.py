from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import pandas as pd
import streamlit as st


@dataclass(frozen=True)
class SheetRef:
    spreadsheet_id: str
    gid: str


def parse_sheet_url(url: str) -> SheetRef:
    match = re.search(r"/spreadsheets/d/([^/]+)", url)
    if not match:
        raise ValueError("URL Google Sheets non valido.")
    parsed = urlparse(url)
    gid = parse_qs(parsed.query).get("gid", ["0"])[0]
    if parsed.fragment.startswith("gid="):
        gid = parsed.fragment.removeprefix("gid=")
    return SheetRef(match.group(1), gid)


def csv_export_url(url: str) -> str:
    ref = parse_sheet_url(url)
    return f"https://docs.google.com/spreadsheets/d/{ref.spreadsheet_id}/export?format=csv&gid={ref.gid}"


@st.cache_data(ttl=600, show_spinner=False)
def load_public_sheet(url: str) -> pd.DataFrame:
    return pd.read_csv(csv_export_url(url), header=None, dtype=str, keep_default_na=False)


@st.cache_data(ttl=600, show_spinner=False)
def load_private_sheet(url: str, worksheet_name: str, service_account: dict) -> pd.DataFrame:
    import gspread

    ref = parse_sheet_url(url)
    gc = gspread.service_account_from_dict(service_account)
    values = gc.open_by_key(ref.spreadsheet_id).worksheet(worksheet_name).get_all_values()
    return pd.DataFrame(values)


def checkbox_value(value: object) -> bool | None:
    text = str(value).strip().lower()
    if text in {"true", "vero", "si", "sì", "x", "1", "✓", "☑", "checked"}:
        return True
    if text in {"false", "falso", "no", "0", "☐", "unchecked"}:
        return False
    return None


def first_date(values: list[object], season_year: int | None = None) -> pd.Timestamp | None:
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        short = re.search(r"\b(\d{1,2})/(\d{1,2})\b", text)
        if short and not re.search(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", text):
            day, month = map(int, short.groups())
            year = season_year or pd.Timestamp.today().year
            if month >= 8:
                year -= 1
            return pd.Timestamp(year=year, month=month, day=day)
        parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
        if pd.notna(parsed):
            return parsed.normalize()
    return None


def classify_event(headers: list[object], season_year: int | None = None) -> tuple[str, pd.Timestamp | None, str] | None:
    labels = [str(value).strip() for value in headers if str(value).strip()]
    joined = " ".join(labels)
    date = first_date(headers, season_year)
    if "PAL" in joined.upper():
        return "Palestra", date, joined
    if date is not None and len(labels) > 1:
        return "Allenamento", date, joined
    return None


def find_name_column(raw: pd.DataFrame, first_data_row: int, event_cols: set[int]) -> int:
    candidates = [col for col in range(raw.shape[1]) if col not in event_cols]
    best = max(
        candidates,
        key=lambda col: raw.iloc[first_data_row:, col].astype(str).str.contains(r"[A-Za-zÀ-ÿ]+ [A-Za-zÀ-ÿ]+", regex=True).sum(),
        default=0,
    )
    return int(best)


def parse_roster(raw: pd.DataFrame, header_rows: int = 3, season_year: int | None = None) -> pd.DataFrame:
    rows = []
    event_cols: dict[int, tuple[str, pd.Timestamp | None, str]] = {}
    for col in range(raw.shape[1]):
        event = classify_event(raw.iloc[:header_rows, col].tolist(), season_year)
        if event:
            event_cols[col] = event

    name_col = find_name_column(raw, header_rows, set(event_cols))
    for row_idx in range(header_rows, raw.shape[0]):
        player = str(raw.iat[row_idx, name_col]).strip()
        if not player:
            continue
        for col, (kind, date, label) in event_cols.items():
            present = checkbox_value(raw.iat[row_idx, col])
            if present is None:
                continue
            rows.append(
                {
                    "persona": player,
                    "data": date,
                    "tipo": kind,
                    "evento": label,
                    "ordine": col,
                    "presente": present,
                }
            )
    out = pd.DataFrame(rows, columns=["persona", "data", "tipo", "evento", "ordine", "presente"])
    if not out.empty:
        dates = out[["ordine", "data"]].drop_duplicates().sort_values("ordine")
        out["data"] = out["ordine"].map(dates.assign(data=dates["data"].ffill()).set_index("ordine")["data"])
    return out


def exclude_current_week_gym_absences(data: pd.DataFrame, today: pd.Timestamp | None = None) -> pd.DataFrame:
    today = (today or pd.Timestamp.today()).normalize()
    if today.weekday() == 6:
        return data.copy()
    week_start = today - pd.Timedelta(days=today.weekday())
    week_end = week_start + pd.Timedelta(days=6)
    current_gym_absence = data["tipo"].eq("Palestra") & data["presente"].eq(False) & data["data"].between(week_start, week_end)
    return data[~current_gym_absence].copy()


def annual_matrix(data: pd.DataFrame, total_data: pd.DataFrame | None = None) -> pd.DataFrame:
    if data.empty:
        return pd.DataFrame()
    total_data = data if total_data is None else total_data

    table = data.copy()
    events = table[["ordine", "data", "tipo", "evento"]].drop_duplicates().sort_values("ordine")
    events["evento_colonna"] = events["ordine"].map(lambda order: f"event_{order}")

    table = table.merge(events[["ordine", "evento_colonna"]], on="ordine", how="left")
    matrix = table.pivot_table(index="persona", columns="evento_colonna", values="presente", aggfunc="first")
    matrix = matrix.reindex(columns=events["evento_colonna"]).reset_index()

    totals = total_data.groupby("persona")["presente"].agg(["sum", "count"])
    matrix["Totale"] = (totals["sum"] / totals["count"] * 100).reindex(matrix["persona"]).round(1).to_numpy()
    for kind, column in {"Allenamento": "Campo", "Palestra": "Palestra"}.items():
        subset = total_data[total_data["tipo"].eq(kind)].groupby("persona")["presente"].agg(["sum", "count"])
        matrix[column] = (subset["sum"] / subset["count"] * 100).reindex(matrix["persona"]).round(1).to_numpy()
    return matrix


def annual_event_columns(data: pd.DataFrame) -> list[dict[str, object]]:
    events = data[["ordine", "data", "tipo"]].drop_duplicates().sort_values("ordine")
    dated = events["data"].ffill()
    weeks = dated.map(lambda date: date.isocalendar().week if pd.notna(date) else None)
    columns = []
    previous_week = object()
    for event, week in zip(events.itertuples(index=False), weeks):
        columns.append(
            {
                "column": f"event_{event.ordine}",
                "label": f"{event.data:%d/%m}" if pd.notna(event.data) else "Pal",
                "week_start": bool(columns and week != previous_week),
            }
        )
        previous_week = week
    return columns


def event_weeks(data: pd.DataFrame) -> pd.DataFrame:
    events = data[["ordine", "data"]].drop_duplicates().sort_values("ordine")
    events["week_date"] = events["data"].ffill()
    events["settimana"] = events["week_date"].dt.to_period("W").astype(str)
    return events[["ordine", "settimana"]]


def stats(data: pd.DataFrame, group_by: list[str]) -> pd.DataFrame:
    if data.empty:
        return pd.DataFrame(columns=group_by + ["presenze", "assenze", "totale", "percentuale"])
    if not group_by:
        presenze = int(data["presente"].sum())
        totale = int(data["presente"].count())
        return pd.DataFrame(
            [{"presenze": presenze, "assenze": totale - presenze, "totale": totale, "percentuale": round(presenze / totale * 100, 1)}]
        )
    out = (
        data.groupby(group_by, dropna=False)["presente"]
        .agg(presenze="sum", totale="count")
        .reset_index()
    )
    out["assenze"] = out["totale"] - out["presenze"]
    out["percentuale"] = (out["presenze"] / out["totale"] * 100).round(1)
    return out[group_by + ["presenze", "assenze", "totale", "percentuale"]]


def player_summary(data: pd.DataFrame) -> pd.DataFrame:
    total = stats(data, ["persona"]).rename(
        columns={"presenze": "presenze_totali", "assenze": "assenze_totali", "totale": "eventi_totali", "percentuale": "percentuale_totale"}
    )
    field = stats(data[data["tipo"].eq("Allenamento")], ["persona"]).rename(
        columns={"presenze": "presenze_campo", "assenze": "assenze_campo", "totale": "eventi_campo", "percentuale": "percentuale_campo"}
    )
    gym = stats(data[data["tipo"].eq("Palestra")], ["persona"]).rename(
        columns={"presenze": "presenze_palestra", "assenze": "assenze_palestra", "totale": "eventi_palestra", "percentuale": "percentuale_palestra"}
    )
    return total.merge(field, on="persona", how="left").merge(gym, on="persona", how="left")


def filter_data(
    data: pd.DataFrame,
    players: list[str],
    kinds: list[str],
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
) -> pd.DataFrame:
    filtered = data.copy()
    filtered = filtered[filtered["persona"].isin(players)]
    if kinds:
        filtered = filtered[filtered["tipo"].isin(kinds)]
    dated = filtered["data"].notna()
    if start is not None:
        filtered = filtered[~dated | (filtered["data"] >= start)]
    if end is not None:
        filtered = filtered[~dated | (filtered["data"] <= end)]
    return filtered
