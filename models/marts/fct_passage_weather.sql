-- The island's weather on the day of the closest approach and the days around it (UTC
-- days, like the fixes). The reanalysis starts in 1940.
select
    p.passage_id,
    p.sid,
    p.name,
    p.season,
    p.island,
    p.category,
    p.max_wind_kt_within_100km,
    w.date,
    date_diff(w.date, date(p.closest_time), day) as day_offset,
    w.precipitation_mm,
    w.wind_max_kmh,
    w.gust_max_kmh
from {{ ref("fct_storm_passages") }} as p
inner join {{ ref("stg_island_weather") }} as w
    on w.island = p.island
    and w.date between date_sub(date(p.closest_time), interval 1 day)
    and date_add(date(p.closest_time), interval 1 day)
