-- One row per storm and island it passed within 100 km of.
select
    concat(sid, '-', island) as passage_id,
    sid,
    any_value(name) as name,
    any_value(season) as season,
    island,
    min(distance_km) as closest_km,
    array_agg(iso_time order by distance_km, iso_time limit 1)[offset(0)] as closest_time,
    max(wind_kt) as max_wind_kt_within_100km,
    {{ saffir_simpson("max(wind_kt)") }} as category,
    min(iso_time) as first_time,
    max(iso_time) as last_time
from {{ ref("int_track_points_near_islands") }}
group by sid, island
