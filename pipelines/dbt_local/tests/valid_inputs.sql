select record_key from {{ ref('stg_captures') }}
where feed not in ('vehicle-positions', 'trip-updates', 'service-alerts')
    or (outcome = 'captured' and received_at is null)
    or (received_at is not null and received_at < requested_at)
union all
select p.record_key from {{ ref('stg_positions') }} p
left join {{ ref('stg_captures') }} c on p.capture_id=c.capture_id and p.store_id=c.store_id
where c.record_key is null or not c.successful
