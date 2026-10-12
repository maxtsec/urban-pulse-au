with grid as (
    select w.*, a.area_id, a.boundary_sha256
    from {{ ref('int_windows') }} w cross join {{ input_table('areas') }} a
), measurements as (
    select g.window_start, g.area_id,
        count(distinct p.vehicle_id) as observed_vehicle_count,
        count(p.record_key) as observation_count,
        median(p.position_age_seconds) as median_position_age_seconds,
        count(p.record_key) filter (where p.quality_issue is not null) as quality_issue_count
    from grid g left join (
        select p.*, m.area_id from {{ ref('int_observations') }} p
        join {{ input_table('memberships') }} m using (record_key)
        where m.membership = 'inside'
    ) p on p.area_id = g.area_id and p.received_at >= g.window_start and p.received_at < g.window_end
    group by g.window_start, g.area_id
), conflicts as (
    select g.window_start, g.area_id,
        count(distinct struct_pack(store := p.store_id, vehicle := p.vehicle_id, observed := p.observed_at))
            filter (where p.record_key is not null) as conflict_count
    from grid g left join (
        select p.*, m.area_id from {{ ref('stg_positions') }} p
        join {{ ref('int_observation_conflicts') }} c using (store_id,vehicle_id,observed_at)
        join {{ input_table('memberships') }} m using (record_key)
        where m.membership in ('inside', 'unknown')
    ) p on p.area_id = g.area_id and p.received_at >= g.window_start and p.received_at < g.window_end
    group by g.window_start,g.area_id
), diagnostics as (
    select g.window_start,
        count(p.record_key) filter (where p.latitude is null or p.longitude is null) as unknown_location_count,
        count(p.record_key) filter (where p.vehicle_id is null) as missing_vehicle_id_count
    from {{ ref('int_windows') }} g left join {{ ref('int_observations') }} p
        on p.received_at >= g.window_start and p.received_at < g.window_end
    group by g.window_start
)
select g.dataset_kind, g.window_start, g.window_end, g.area_id, g.boundary_sha256,
    case when c.successful_capture_count = 0
        or (m.observed_vehicle_count = 0 and (x.conflict_count > 0 or d.unknown_location_count > 0 or d.missing_vehicle_id_count > 0))
        then null else m.observed_vehicle_count end as observed_vehicle_count,
    m.observation_count, m.median_position_age_seconds, m.quality_issue_count, x.conflict_count,
    d.unknown_location_count, d.missing_vehicle_id_count,
    c.successful_capture_count, c.failed_capture_count, c.max_success_gap_seconds, c.coverage
from grid g join measurements m using (window_start, area_id)
join diagnostics d using (window_start)
join conflicts x using (window_start,area_id)
join {{ ref('mart_capture_15m') }} c on c.window_start = g.window_start and c.feed = 'vehicle-positions'
