# Home Assistant ResMed myAir Automation

This automation posts nightly CPAP session data from the ResMed AirSense 11 into the datalake as `health.sleep` events.

Uses the [resmed_myair_sensors](https://github.com/prestomation/resmed_myair_sensors) HACS integration, which handles all myAir authentication and creates HA sensor entities updated once daily.

## What it sends

- `source`: `resmed_myair`
- `event_type`: `health.sleep`
- `timestamp`: the current data date from `sensor.airsense11_cpap_current_data_date`
- `payload`: CPAP session metrics

Payload fields:

- `ahi` — apnea-hypopnea index (events/hour)
- `mask_leak` — mask leak rate
- `mask_on_count` — mask on/off count
- `sleep_score` — total myAir score (0–100)
- `usage_minutes` — total usage in minutes

## HA entities

| Entity | Description |
|---|---|
| `sensor.airsense11_cpap_ahi_events_per_hour` | AHI — apnea events per hour |
| `sensor.airsense11_cpap_mask_leak` | Mask leak rate |
| `sensor.airsense11_cpap_mask_on_off` | Number of times mask was put on |
| `sensor.airsense11_cpap_total_myair_score` | Overall myAir sleep score |
| `sensor.airsense11_cpap_usage_minutes` | Minutes of device usage |
| `sensor.airsense11_cpap_current_data_date` | Date the current session data relates to |
| `sensor.airsense11_cpap_sleep_data_last_collected` | When HA last synced from myAir |

## Trigger

Watch `sensor.airsense11_cpap_sleep_data_last_collected` for a state change — this updates once daily when the integration pulls fresh data from myAir. Add a 30-second debounce to avoid duplicate triggers.

## Home Assistant config

```yaml
automation:
  - alias: "Push ResMed sleep data to datalake"
    mode: single
    trigger:
      - platform: state
        entity_id: sensor.airsense11_cpap_sleep_data_last_collected
        for:
          seconds: 30
    condition:
      - condition: template
        value_template: >
          {{ states('sensor.airsense11_cpap_current_data_date') not in ['', 'unknown', 'unavailable'] }}
    action:
      - service: rest_command.datalake_push_resmed
        data:
          data_date: "{{ states('sensor.airsense11_cpap_current_data_date') }}"
          ahi: "{{ states('sensor.airsense11_cpap_ahi_events_per_hour') }}"
          mask_leak: "{{ states('sensor.airsense11_cpap_mask_leak') }}"
          mask_on_count: "{{ states('sensor.airsense11_cpap_mask_on_off') }}"
          sleep_score: "{{ states('sensor.airsense11_cpap_total_myair_score') }}"
          usage_minutes: "{{ states('sensor.airsense11_cpap_usage_minutes') }}"

rest_command:
  datalake_push_resmed:
    url: "http://docker.home:8000/events"
    method: POST
    headers:
      Authorization: !secret datalake_token
      Content-Type: application/json
    payload: >
      {
        "source": "resmed_myair",
        "event_type": "health.sleep",
        "timestamp": "{{ data_date }}T00:00:00+02:00",
        "payload": {
          "ahi": {{ ahi | float | round(2) | tojson }},
          "mask_leak": {{ mask_leak | float | round(2) | tojson }},
          "mask_on_count": {{ mask_on_count | int | tojson }},
          "sleep_score": {{ sleep_score | int | tojson }},
          "usage_minutes": {{ usage_minutes | int | tojson }}
        }
      }
```

## Secrets

`datalake_token` must be set in `secrets.yaml`:

```yaml
datalake_token: "Bearer mytoken"
```

## Deduplication

The trigger fires once per day when myAir syncs. If you want an extra safety net against duplicate entries, add a condition checking the datalake before posting — but in practice a single daily trigger with `mode: single` is sufficient.

## Notes

- The timestamp uses `data_date` (the date the sleep session relates to) rather than `now()`, so the event is correctly attributed to the night it occurred rather than when HA polled myAir.
- The `+02:00` timezone offset assumes CET/CEST (Sweden). Adjust if needed.
- `rest_command` requires a **full HA restart** to take effect — "Reload core" is not enough.
- Always use `| tojson` for nullable sensor values — bare Jinja2 renders unavailable sensors as `None` (invalid JSON).

## Example event

```json
{
  "source": "resmed_myair",
  "event_type": "health.sleep",
  "timestamp": "2026-05-07T00:00:00+02:00",
  "payload": {
    "ahi": 2.8,
    "mask_leak": 6.4,
    "mask_on_count": 1,
    "sleep_score": 84,
    "usage_minutes": 432
  }
}
```
