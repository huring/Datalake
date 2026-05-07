# Home Assistant Roborock Automation

This automation posts Roborock cleaning runs into the datalake as `clean.completed` events.

Use it when your vacuum is already exposed in Home Assistant and you want a simple history of completed runs without adding any extra collectors or cloud dependencies.

## What it sends

- `source`: `roborock`
- `event_type`: `clean.completed`
- `timestamp`: the current HA time in ISO 8601 format
- `payload`: run stats captured from the vacuum entity

Recommended payload fields:

- `duration_seconds`
- `area_m2`
- `device`

## Home Assistant config

```yaml
# configuration.yaml or a package file
automation:
  - alias: "Push vacuum run to datalake"
    mode: queued
    trigger:
      - platform: state
        entity_id: vacuum.roborock_s6_maxv  # change to your vacuum entity
        to: "docked"
        for:
          seconds: 10  # debounce dock jitter and short reconnect noise
    action:
      - service: rest_command.datalake_push_vacuum
        data:
          duration: "{{ state_attr('vacuum.roborock_s6_maxv', 'last_run_stats').total_time | default(0) }}"
          area: "{{ (state_attr('vacuum.roborock_s6_maxv', 'last_run_stats').area | float / 1000000) | round(2) }}"

rest_command:
  datalake_push_vacuum:
    url: "http://docker.home:8000/events"
    method: POST
    headers:
      Authorization: !secret datalake_token
      Content-Type: application/json
    payload: >
      {
        "source": "roborock",
        "event_type": "clean.completed",
        "timestamp": "{{ now().isoformat() }}",
        "payload": {
          "duration_seconds": {{ duration }},
          "area_m2": {{ area }},
          "device": "roborock_s6_maxv"
        }
      }
```

## Secrets

Set `datalake_token` in `secrets.yaml` to the same value as the API token used by the datalake stack.

```yaml
datalake_token: "your-shared-token"
```

## Why this trigger

The Roborock integration already exposes run stats in Home Assistant, and the docked transition is the cleanest reliable moment to publish a completed-cleaning event. The 10 second delay helps avoid state bounce when the vacuum reconnects or the dock transition is noisy.

## Example event shape

```json
{
  "source": "roborock",
  "event_type": "clean.completed",
  "timestamp": "2026-05-07T21:00:00+02:00",
  "payload": {
    "duration_seconds": 1800,
    "area_m2": 42.5,
    "device": "roborock_s6_maxv"
  }
}
```
