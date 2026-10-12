-- Equal source identity/time with different coordinates or trip is not a safe resend.
select store_id, vehicle_id, observed_at
from {{ ref('stg_positions') }}
where vehicle_id is not null and observed_at is not null
group by store_id, vehicle_id, observed_at
having count(distinct struct_pack(lat := latitude, lon := longitude,
    trip := trip_id, route := route_id, service_date := start_date, start_time := start_time)) > 1
