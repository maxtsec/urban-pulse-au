-- Keep the earliest received copy within each 15-minute receipt window.
-- Missing identity/time cannot establish a duplicate, so retain separate source rows.
select * exclude (duplicate_rank) from (
    select *, row_number() over (
        partition by store_id, vehicle_id, observed_at, time_bucket(interval '15 minutes', received_at),
            case when vehicle_id is null or observed_at is null then record_key end
        order by received_at, record_key
    ) as duplicate_rank
    from {{ ref('stg_positions') }} p
    where not exists (
        select 1 from {{ ref('int_observation_conflicts') }} c
        where c.store_id = p.store_id and c.vehicle_id = p.vehicle_id
            and c.observed_at = p.observed_at
    )
) where duplicate_rank = 1
