{{
    config(
        materialized="incremental",
        unique_key=["island", "date"],
        partition_by={"field": "date", "data_type": "date", "granularity": "month"},
        cluster_by=["island"],
    )
}}

select island, date, precipitation_mm, wind_max_kmh, gust_max_kmh
from {{ source("raw", "island_weather") }}
{% if is_incremental() %}
where date > (select date_sub(max(date), interval 10 day) from {{ this }})
{% endif %}
