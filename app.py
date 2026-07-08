import html
from pathlib import Path
import tomllib

import altair as alt
import pandas as pd
import streamlit as st

from attendance import annual_event_columns, annual_matrix, event_weeks, exclude_current_week_gym_absences, filter_data, load_private_sheet, load_public_sheet, parse_roster, player_summary, stats


EXCLUDED_PLAYERS = (
    "Baraldi Federico",
    "Bellofiore",
    "Bruni",
    "Cannata",
    "Contini",
    "Dellavedova",
    "Di Vietro",
    "Fabbrini",
    "Montanari",
    "Panariello",
    "Pari",
    "Parodi",
    "Poggi",
    "Sangiorgi",
    "Sarais",
    "Spigato",
    "Vlieghe",
    "Zocca",
)


def default_players(players: list[str]) -> list[str]:
    return [player for player in players if not any(name.lower() in player.lower() for name in EXCLUDED_PLAYERS)]


def sheet_url() -> str:
    url = st.secrets.get("sheet_url")
    for path in (Path("streamlit/secrets.toml"), Path(".streamlit/secrets.toml")):
        if url or not path.exists():
            continue
        with path.open("rb") as file:
            url = tomllib.load(file).get("sheet_url")
    if not url:
        st.error("Configura `sheet_url` in `streamlit/secrets.toml` o nei Secrets di Streamlit Cloud.")
        st.stop()
    return url


def percent_style(value: object) -> str:
    if pd.isna(value):
        return ""
    if value >= 78:
        return "color: #16a34a; font-weight: 700"
    if value >= 63:
        return "color: #ca8a04; font-weight: 700"
    return "color: #dc2626; font-weight: 700"


def percent_table(table: pd.DataFrame, columns: dict[str, str], percent_column: str) -> object:
    display = table.rename(columns=columns)
    return display.style.format({columns[percent_column]: "{:.1f}%"}).map(percent_style, subset=[columns[percent_column]])


def render_annual_table(matrix: pd.DataFrame, events: list[dict[str, object]]) -> None:
    event_cols = [event["column"] for event in events]
    right_cols = ["Totale", "Campo", "Palestra"]
    col_count = len(event_cols) + 4

    header = ['<th class="sticky-left name">Nome</th>']
    for event in events:
        klass = " week-start" if event["week_start"] else ""
        header.append(f'<th class="event{klass}">{html.escape(str(event["label"]))}</th>')
    for index, col in enumerate(right_cols):
        header.append(f'<th class="sticky-right total total-{index}">{col}</th>')

    rows = []
    for row in matrix.itertuples(index=False):
        values = row._asdict()
        cells = [f'<td class="sticky-left name">{html.escape(str(values["persona"]))}</td>']
        for event in events:
            col = str(event["column"])
            checked = " checked" if values.get(col) == True else ""
            klass = " week-start" if event["week_start"] else ""
            cells.append(f'<td class="event{klass}"><input type="checkbox" disabled{checked}></td>')
        for index, col in enumerate(right_cols):
            value = values.get(col)
            text = "" if pd.isna(value) else f"{value:.1f}%"
            style = percent_style(value)
            cells.append(f'<td class="sticky-right total total-{index}"><span style="{style}">{text}</span></td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")

    st.markdown(
        f"""
        <style>
        .annual-wrap {{
            max-height: 720px;
            overflow: auto;
            border: 1px solid rgba(250, 250, 250, .18);
            border-radius: 6px;
        }}
        .annual-table {{
            border-collapse: separate;
            border-spacing: 0;
            min-width: {max(980, col_count * 42)}px;
            font-size: 13px;
        }}
        .annual-table th, .annual-table td {{
            border-right: 1px solid rgba(250, 250, 250, .14);
            border-bottom: 1px solid rgba(250, 250, 250, .12);
            background: var(--background-color);
            color: var(--text-color);
            height: 30px;
            min-width: 42px;
            padding: 4px 6px;
            text-align: center;
            white-space: nowrap;
        }}
        .annual-table th {{
            position: sticky;
            top: 0;
            z-index: 3;
            background: var(--secondary-background-color);
            font-weight: 600;
        }}
        .annual-table .week-start {{
            border-left: 3px solid var(--primary-color);
        }}
        .annual-table .name {{
            left: 0;
            min-width: 190px;
            max-width: 190px;
            text-align: left;
            font-weight: 600;
            z-index: 4;
        }}
        .annual-table .sticky-left {{
            position: sticky;
        }}
        .annual-table .sticky-right {{
            position: sticky;
            z-index: 4;
            min-width: 72px;
            font-weight: 600;
        }}
        .annual-table th.sticky-right {{
            z-index: 5;
        }}
        .annual-table .total-2 {{ right: 0; }}
        .annual-table .total-1 {{ right: 72px; }}
        .annual-table .total-0 {{ right: 144px; }}
        .annual-table input {{
            width: 16px;
            height: 16px;
            margin: 0;
        }}
        </style>
        <div class="annual-wrap">
            <table class="annual-table">
                <thead><tr>{''.join(header)}</tr></thead>
                <tbody>{''.join(rows)}</tbody>
            </table>
        </div>
        """,
        unsafe_allow_html=True,
    )


def pie_data(label: str, data: pd.DataFrame) -> pd.DataFrame:
    present = int(data["presente"].sum()) if not data.empty else 0
    total = int(data["presente"].count()) if not data.empty else 0
    return pd.DataFrame(
        {
            "gruppo": [label, label],
            "esito": ["Presenza", "Assenza"],
            "valore": [present, max(total - present, 0)],
        }
    )


def pie_chart(title: str, player_data: pd.DataFrame, team_data: pd.DataFrame) -> None:
    chart_data = pd.concat([pie_data("Giocatore", player_data), pie_data("Squadra", team_data)])
    chart = (
        alt.Chart(chart_data)
        .mark_arc()
        .encode(theta="valore:Q", color="esito:N", column=alt.Column("gruppo:N", title=None))
        .properties(title=title, height=180)
    )
    st.altair_chart(chart, width="stretch")


def apply_period(data: pd.DataFrame, mode: str, weeks: int, date_range: tuple | None) -> pd.DataFrame:
    dated = data[data["data"].notna()]
    if dated.empty:
        return data
    if mode == "Tutto l'anno":
        return data
    if mode == "Ultime N settimane":
        return filter_data(data, sorted(data["persona"].unique()), sorted(data["tipo"].unique()), dated["data"].max() - pd.Timedelta(weeks=int(weeks)), None)
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start, end = map(pd.Timestamp, date_range)
        return filter_data(data, sorted(data["persona"].unique()), sorted(data["tipo"].unique()), start, end)
    return data


st.set_page_config(page_title="Attendance Stats", layout="wide")
st.title("Attendance Stats")

try:
    roster_url = sheet_url()
    if "gcp_service_account" in st.secrets:
        raw = load_private_sheet(roster_url, "Roster", dict(st.secrets["gcp_service_account"]))
    else:
        raw = load_public_sheet(roster_url)
    data = exclude_current_week_gym_absences(parse_roster(raw, 3, pd.Timestamp.today().year))
except Exception as exc:
    st.error(f"Non riesco a leggere il foglio: {exc}")
    st.stop()

if data.empty:
    st.warning("Nessuna presenza trovata.")
    st.stop()

players_all = sorted(data["persona"].unique())
dated = data[data["data"].notna()]
min_date = dated["data"].min().date() if not dated.empty else None
max_date = dated["data"].max().date() if not dated.empty else None

with st.sidebar:
    page = st.radio("Pagina", ["Statistiche", "Anno", "Giocatore"])
    players = st.multiselect("Persone", players_all, default=default_players(players_all))
    kinds = st.multiselect("Tipo evento", sorted(data["tipo"].unique()), default=sorted(data["tipo"].unique()))
    period_mode = None
    date_range = None
    last_weeks = 4
    if page == "Statistiche":
        period_mode = st.radio("Periodo", ["Ultime N settimane", "Range date", "Tutto l'anno"])
        if period_mode == "Ultime N settimane":
            last_weeks = st.number_input("Settimane", min_value=1, max_value=52, value=4)
        elif period_mode == "Range date":
            default_start = (pd.Timestamp(max_date) - pd.Timedelta(weeks=4)).date() if max_date else min_date
            date_range = st.date_input("Range date", value=(default_start, max_date) if min_date else None)

filtered = filter_data(data, players, kinds, None, None)
if page == "Statistiche":
    filtered = apply_period(filtered, period_mode or "Ultime N settimane", int(last_weeks), date_range)
if filtered.empty:
    st.warning("Nessun dato con questi filtri.")
    st.stop()

total = stats(filtered, [])
training = stats(filtered[filtered["tipo"].eq("Allenamento")], [])
gym = stats(filtered[filtered["tipo"].eq("Palestra")], [])

cols = st.columns(3)
cols[0].metric("Presenze totali", f"{total['percentuale'].iat[0] if not total.empty else 0:.1f}%")
cols[1].metric("Presenze campo allenamento", f"{training['percentuale'].iat[0] if not training.empty else 0:.1f}%")
cols[2].metric("Presenze palestra", f"{gym['percentuale'].iat[0] if not gym.empty else 0:.1f}%")

if page == "Anno":
    weeks = event_weeks(filtered)
    options = weeks["settimana"].dropna().drop_duplicates().to_list()
    default_weeks = options[-4:]
    with st.sidebar:
        selected_weeks = st.multiselect("Settimane", options, default=default_weeks)
    orders = weeks[weeks["settimana"].isin(selected_weeks)]["ordine"]
    annual_data = filtered[filtered["ordine"].isin(orders)]
    if annual_data.empty:
        st.warning("Nessuna settimana selezionata.")
        st.stop()
    render_annual_table(annual_matrix(annual_data, filtered), annual_event_columns(annual_data))

elif page == "Statistiche":
    summary = player_summary(filtered).sort_values("percentuale_totale", ascending=False)

    st.subheader("Totale")
    total_table = summary[["persona", "presenze_totali", "assenze_totali", "eventi_totali", "percentuale_totale"]]
    st.dataframe(
        percent_table(
            total_table,
            {
                "persona": "Giocatore",
                "presenze_totali": "Presenze",
                "assenze_totali": "Assenze",
                "eventi_totali": "Eventi",
                "percentuale_totale": "% Totale",
            },
            "percentuale_totale",
        ),
        width="stretch",
        hide_index=True,
    )

    field_col, gym_col = st.columns(2)
    with field_col:
        st.subheader("Presenze Campo")
        field_table = summary[["persona", "presenze_campo", "assenze_campo", "eventi_campo", "percentuale_campo"]].sort_values("percentuale_campo", ascending=False)
        st.dataframe(
            percent_table(
                field_table,
                {
                    "persona": "Giocatore",
                    "presenze_campo": "Presenze Campo",
                    "assenze_campo": "Assenze Campo",
                    "eventi_campo": "Eventi",
                    "percentuale_campo": "% Totale",
                },
                "percentuale_campo",
            ),
            width="stretch",
            hide_index=True,
        )
    with gym_col:
        st.subheader("Presenze Palestra")
        gym_table = summary[["persona", "presenze_palestra", "assenze_palestra", "eventi_palestra", "percentuale_palestra"]].sort_values("percentuale_palestra", ascending=False)
        st.dataframe(
            percent_table(
                gym_table,
                {
                    "persona": "Giocatore",
                    "presenze_palestra": "Presenze Palestra",
                    "assenze_palestra": "Assenze Palestra",
                    "eventi_palestra": "Eventi",
                    "percentuale_palestra": "% Totale",
                },
                "percentuale_palestra",
            ),
            width="stretch",
            hide_index=True,
        )

else:
    player = st.selectbox("Giocatore", sorted(filtered["persona"].unique()))
    one = filtered[filtered["persona"].eq(player)]
    st.dataframe(stats(one, ["tipo"]), width="stretch", hide_index=True)

    chart_cols = st.columns(3)
    with chart_cols[0]:
        pie_chart("Totale", one, filtered)
    with chart_cols[1]:
        pie_chart("Campo", one[one["tipo"].eq("Allenamento")], filtered[filtered["tipo"].eq("Allenamento")])
    with chart_cols[2]:
        pie_chart("Palestra", one[one["tipo"].eq("Palestra")], filtered[filtered["tipo"].eq("Palestra")])

    st.dataframe(one.sort_values(["data", "tipo", "evento"]), width="stretch", hide_index=True)
