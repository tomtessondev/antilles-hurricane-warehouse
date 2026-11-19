"""README charts from the marts (a few KB read): hurricane passages per decade and per
island. Run with application-default credentials: `python scripts/charts.py`."""

from __future__ import annotations

import os
from pathlib import Path

import matplotlib.pyplot as plt
from google.cloud import bigquery

OUT = Path(__file__).resolve().parents[1] / "docs" / "images"
CATEGORIES = ["Cat 1", "Cat 2", "Cat 3", "Cat 4", "Cat 5"]
# One blue, light to dark: the category is ordered, so its colour is too.
COLORS = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"]
SURFACE, INK, MUTED = "#fcfcfb", "#0b0b0b", "#52514e"
CAP = bigquery.QueryJobConfig(maximum_bytes_billed=100_000_000)


def style(ax: plt.Axes) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(MUTED)
    ax.tick_params(colors=MUTED, length=0)
    ax.grid(axis="y", color="#e4e3df", linewidth=0.8)
    ax.set_axisbelow(True)


def by_decade(bq: bigquery.Client, project: str) -> None:
    rows = bq.query(
        f"""
        SELECT decade, category, COUNT(DISTINCT sid) AS storms
        FROM `{project}.marts.fct_storm_passages`
        CROSS JOIN UNNEST([DIV(season, 10) * 10]) AS decade
        WHERE category LIKE 'Cat %'
        GROUP BY decade, category
        """,
        job_config=CAP,
    ).result()
    counts: dict[tuple[int, str], int] = {(r.decade, r.category): r.storms for r in rows}
    decades = list(range(1850, max(d for d, _ in counts) + 10, 10))

    fig, ax = plt.subplots(figsize=(10, 4.2), facecolor=SURFACE)
    style(ax)
    bottom = [0] * len(decades)
    for category, color in zip(CATEGORIES, COLORS, strict=True):
        heights = [counts.get((d, category), 0) for d in decades]
        ax.bar(decades, heights, width=8, bottom=bottom, color=color, label=category,
               edgecolor=SURFACE, linewidth=1)  # fmt: skip
        bottom = [b + h for b, h in zip(bottom, heights, strict=True)]
    ax.set_xticks(decades[::2], [f"{d}s" for d in decades[::2]], color=MUTED)
    ax.set_ylabel("hurricanes", color=MUTED)
    ax.set_title("Hurricanes passing within 100 km of an island, per decade",
                 loc="left", color=INK, fontsize=12, pad=30)  # fmt: skip
    ax.legend(frameon=False, ncols=5, loc="lower left", bbox_to_anchor=(0, 1), labelcolor=MUTED)
    fig.tight_layout()
    fig.savefig(OUT / "hurricanes_per_decade.png", dpi=150)


def by_island(bq: bigquery.Client, project: str) -> None:
    rows = list(
        bq.query(
            f"""
            SELECT island, category, COUNT(*) AS passages
            FROM `{project}.marts.fct_storm_passages`
            WHERE category LIKE 'Cat %' AND season >= 1950
            GROUP BY island, category
            """,
            job_config=CAP,
        ).result()
    )
    counts = {(r.island, r.category): r.passages for r in rows}
    islands = sorted({r.island for r in rows},
                     key=lambda i: sum(counts.get((i, c), 0) for c in CATEGORIES))  # fmt: skip

    fig, ax = plt.subplots(figsize=(10, 3.8), facecolor=SURFACE)
    style(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color="#e4e3df", linewidth=0.8)
    left = [0] * len(islands)
    for category, color in zip(CATEGORIES, COLORS, strict=True):
        widths = [counts.get((i, category), 0) for i in islands]
        ax.barh(islands, widths, left=left, color=color, label=category, height=0.6,
                edgecolor=SURFACE, linewidth=1)  # fmt: skip
        left = [a + w for a, w in zip(left, widths, strict=True)]
    for y, total in enumerate(left):
        ax.text(total + 0.3, y, str(total), va="center", color=INK, fontsize=9)
    ax.tick_params(axis="y", colors=INK)
    ax.set_xlabel("hurricanes within 100 km since 1950", color=MUTED)
    ax.set_title(
        "Hurricane passages per island since 1950", loc="left", color=INK, fontsize=12, pad=30
    )
    ax.legend(frameon=False, ncols=5, loc="lower left", bbox_to_anchor=(0, 1), labelcolor=MUTED)
    fig.tight_layout()
    fig.savefig(OUT / "hurricanes_per_island.png", dpi=150)


if __name__ == "__main__":
    project = os.getenv("GCP_PROJECT", "antilles-hurricanes")
    client = bigquery.Client(project=project)
    by_decade(client, project)
    by_island(client, project)
