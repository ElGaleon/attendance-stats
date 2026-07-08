import pandas as pd

from attendance import annual_event_columns, annual_matrix, checkbox_value, exclude_current_week_gym_absences, parse_roster, player_summary, stats


def test_parse_roster_counts_training_and_gym():
    raw = pd.DataFrame(
        [
            ["Nome", "01/07/2026", "PAL 03/07/2026", ""],
            ["", "Campo A", "", ""],
            ["Ada", "TRUE", "FALSE", ""],
            ["Bruno", "FALSE", "TRUE", ""],
            ["Carla", "", "TRUE", ""],
        ]
    )

    data = parse_roster(raw, header_rows=2)

    assert len(data) == 5
    assert set(data["tipo"]) == {"Allenamento", "Palestra"}
    assert stats(data, [])["percentuale"].iat[0] == 60.0
    assert stats(data[data["tipo"].eq("Allenamento")], [])["percentuale"].iat[0] == 50.0
    assert stats(data[data["tipo"].eq("Palestra")], [])["percentuale"].iat[0] == round(2 / 3 * 100, 1)

    matrix = annual_matrix(data)
    columns = annual_event_columns(data)
    event_columns = [col for col in matrix.columns if col.startswith("event_")]
    assert columns[0]["label"] == "01/07"
    assert matrix.loc[matrix["persona"].eq("Ada"), event_columns[0]].iat[0] == True
    assert matrix.loc[matrix["persona"].eq("Ada"), event_columns[1]].iat[0] == False
    assert matrix.loc[matrix["persona"].eq("Ada"), "Totale"].iat[0] == 50.0
    ada = player_summary(data).loc[lambda df: df["persona"].eq("Ada")].iloc[0]
    assert ada["percentuale_palestra"] == 0.0
    assert ada["presenze_campo"] == 1
    assert ada["assenze_palestra"] == 1


def test_undated_gym_stays_in_previous_week():
    raw = pd.DataFrame(
        [
            ["Nome", "01/07/2026", "PAL", "08/07/2026"],
            ["", "Campo A", "Level24", "Campo A"],
            ["Ada", "TRUE", "TRUE", "TRUE"],
        ]
    )

    data = parse_roster(raw, header_rows=2)
    columns = annual_event_columns(data)

    assert [col["week_start"] for col in columns] == [False, False, True]
    assert data[data["tipo"].eq("Palestra")]["data"].iat[0] == pd.Timestamp("2026-07-01")


def test_checkbox_values():
    assert checkbox_value("TRUE") is True
    assert checkbox_value("FALSE") is False
    assert checkbox_value("") is None


def test_current_week_gym_absences_are_excluded():
    data = pd.DataFrame(
        [
            {"persona": "Ada", "data": pd.Timestamp("2026-07-06"), "tipo": "Palestra", "evento": "Pal", "ordine": 1, "presente": False},
            {"persona": "Ada", "data": pd.Timestamp("2026-07-07"), "tipo": "Palestra", "evento": "Pal", "ordine": 2, "presente": True},
            {"persona": "Ada", "data": pd.Timestamp("2026-07-08"), "tipo": "Allenamento", "evento": "Campo", "ordine": 3, "presente": False},
            {"persona": "Ada", "data": pd.Timestamp("2026-06-30"), "tipo": "Palestra", "evento": "Pal", "ordine": 4, "presente": False},
        ]
    )

    filtered = exclude_current_week_gym_absences(data, pd.Timestamp("2026-07-08"))

    assert len(filtered) == 3
    assert not ((filtered["tipo"].eq("Palestra")) & (filtered["data"].eq(pd.Timestamp("2026-07-06")))).any()
    assert len(exclude_current_week_gym_absences(data, pd.Timestamp("2026-07-12"))) == 4
