{#- Incremental by season partition: a daily run rewrites the current and previous seasons
    only (the storms being tracked, and late revisions). `dbt build --full-refresh`
    rebuilds every season. -#}
{{
    config(
        materialized="incremental",
        incremental_strategy="insert_overwrite",
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
{% if is_incremental() %}
where season >= extract(year from current_date()) - 1
{% endif %}
