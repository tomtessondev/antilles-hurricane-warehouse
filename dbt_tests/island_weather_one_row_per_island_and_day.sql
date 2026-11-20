-- Two loads running at once (the daily workflow and a manual `make load`) could each delete
-- then append the same days: duplicates in raw would make the staging MERGE fail. This
-- test names them first.
select island, date, count(*) as copies
from {{ source("raw", "island_weather") }}
group by island, date
having count(*) > 1
