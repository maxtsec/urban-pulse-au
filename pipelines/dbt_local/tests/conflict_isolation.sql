select p.record_key from {{ ref('int_observations') }} p
join {{ ref('int_observation_conflicts') }} c using (store_id,vehicle_id,observed_at)
