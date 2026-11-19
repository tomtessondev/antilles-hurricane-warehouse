{#- A full table, rebuilt every run: NOAA revises past seasons, and the whole history is
    8 MB, so an incremental model would save almost nothing and keep stale seasons. -#}
{{
    config(
        materialized="table",
        partition_by={
            "field": "season",
            "data_type": "int64",
            "range": {"start": 1850, "end": 2101, "interval": 1},
        },
        cluster_by=["sid"],
    )
}}

select
    sid,
    name,
    season,
    iso_time,
    nature,
    lat,
    lon,
    wind_kt,
    pressure_hpa
from {{ source("raw", "tracks") }}
