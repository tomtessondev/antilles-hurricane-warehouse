-- Every track fix within 100 km of an island's point, with its distance.
with islands as (
    select name as island, st_geogpoint(lon, lat) as point from {{ ref("islands") }}
)

select
    t.sid,
    t.name,
    t.season,
    t.iso_time,
    t.nature,
    t.wind_kt,
    i.island,
    st_distance(st_geogpoint(t.lon, t.lat), i.point) / 1000 as distance_km
from {{ ref("stg_tracks") }} as t
inner join islands as i
    on st_dwithin(st_geogpoint(t.lon, t.lat), i.point, 100000)
